# RFC-0001: Core Operational Reasoning Architecture

| Field | Value |
|-------|-------|
| Status | **Accepted** |
| Date | 2026-06-26 (reconstructed) |
| Supersedes | — |
| Extended by | [RFC-0002: Multi-Signal Reasoning](RFC-0002-multi-signal-reasoning.md) |
| Related | [architecture.md](../architecture.md), [reasoning-pipeline.md](../reasoning-pipeline.md) |

## Summary

This RFC documents the foundational architecture of ODIS as implemented in the codebase. It is a historical reconstruction of decisions already accepted, built, tested, and described across the README, architecture documentation, examples, and test suite.

It is not a new design proposal. Where early discussions diverged from implementation, **the implementation is authoritative**.

---

## 1. Context

Industrial systems produce continuous measurements — temperature, pressure, flow rate, voltage, and more. Dashboards display values; they do not explain what those values mean operationally or what should be done about them.

ODIS exists to transform **raw operational observations** into **explainable operational decisions** through an explicit, auditable reasoning chain.

The central challenge is not computation. It is **structure**: separating what was measured from what was detected, what was assessed, and what was recommended — so that reasoning can be tested, replayed, and extended without rewriting history.

### Four concepts

ODIS organizes reasoning around four distinctions that remain separate throughout the pipeline:

| Concept | Question | Layer |
|---------|----------|-------|
| **Evidence** | What was measured? | Domain (`Observation`) |
| **Signal** | What pattern was detected? | Application (`TrendDetector` → `DetectedTrend`) |
| **Assessment** | What does it mean operationally? | Domain (`OperationalSituation`) |
| **Decision** | What should be done? | Domain (`DecisionPlan`) |

Collapsing these stages — for example, storing trend direction directly on a plan — would reduce traceability and make the system harder to evolve.

---

## 2. Design Goals

The following principles guided implementation and are enforced across the codebase:

**Explainable reasoning.** Every recommendation includes a justification. Reasoning is deterministic and inspectable — not opaque automation.

**Immutable domain entities.** All domain records are frozen after creation. Change is expressed as new snapshots, not in-place mutation.

**Append-only history.** Observations accumulate. Situations, contexts, and plans are appended to the operational record. Prior states are never rewritten.

**Industry-agnostic core.** The domain model uses generic types (`Asset`, `MeasurementType`, `Observation`) without sector-specific enums, taxonomies, or thresholds.

**Deterministic behavior.** The pipeline uses explicit logic. No machine learning, probabilistic models, or AI components exist in the reasoning path.

**Layered architecture.** Domain, application, and infrastructure (reserved) are separated. Dependencies point inward.

**Replaceable application components.** Detectors, assessors, and planners are independent classes or functions that can be swapped or extended without changing domain entities.

---

## 3. Architectural Decisions

### Domain layer (`src/domain/`)

The domain defines **what operational reasoning means** in ODIS.

**Immutable entities** record identity and relationships:

- `Asset`, `Observation`, `OperationalGoal`
- `OperationalSituation`, `DecisionContext`, `DecisionPlan`
- `Action`, `Outcome` (recorded by the executable pipeline; not yet fed back into future decisions)

All entities use frozen dataclasses. Structural invariants (non-empty identifiers, required fields) are enforced in `__post_init__`.

**Value objects** express typed attributes without identity:

- `MeasurementType`, `Location`, `Priority`, `TrendDirection`
- `DetectedTrend` (signal result type, consumed by application layer)
- Others (`Confidence`, `Severity`, `TimeRange`, `Constraint`, `Policy`) defined for future use

**Events** are contracts for facts that already happened:

- `ObservationRecorded`, `OperationalSituationCreated`
- `DecisionContextCreated`, `DecisionPlanGenerated`, `OutcomeRecorded`

Event types exist. No event bus or dispatcher is implemented.

**Repository interfaces** define persistence contracts without implementation:

- `ObservationRepository`, `SituationRepository`, `DecisionRepository`

The domain imports nothing from application or infrastructure code.

### Application layer (`src/application/`)

The application layer defines **how reasoning is performed** by orchestrating domain objects.

| Component | Responsibility |
|-----------|----------------|
| `TrendDetector` | Derives `DetectedTrend` from an observation sequence |
| `OperationalSituationAssessor` | Combines evidence, signal, and goal into `OperationalSituation` |
| `create_decision_context` | Snapshots planner inputs as `DecisionContext` |
| `DecisionPlanner` | Produces `DecisionPlan` from `DecisionContext` |
| `create_operational_situation` | Constructs `OperationalSituation` without signal-based assessment (lower-level orchestration) |

Application code validates input coherence (e.g., observations share an asset and measurement type). Domain invariants remain on entities.

Detectors produce signals. Assessors produce assessments. Planners produce recommendations. These roles do not overlap.

### Infrastructure layer (`src/infrastructure/`)

Reserved for future adapters:

- Repository implementations
- Telemetry ingestion
- Event dispatch
- External system integration

The directory exists as a placeholder. No infrastructure code is implemented.

### Verification and demonstration

- **`tests/`** — behavioral specifications with reusable builders
- **`examples/`** — executable walkthroughs (heatwave, stable, oscillating scenarios) wiring the same application pipeline

Both depend on application and domain layers. Neither is imported by production code.

---

## 4. Reasoning Pipeline

The accepted pipeline transforms evidence into decisions through explicit stages:

```
Observation
      ↓
DetectedTrend
      ↓
OperationalSituation
      ↓
DecisionContext
      ↓
DecisionPlan
      ↓
Action          (recorded by the executable pipeline)
      ↓
Outcome         (recorded by the executable pipeline)
```

### Stage responsibilities

**Observation** — Immutable evidence. A measurement recorded from the environment: asset, timestamp, value, unit, measurement type. Observations do not interpret themselves.

**DetectedTrend** — Signal. Produced by `TrendDetector` from a homogeneous observation sequence. Compares first and last values after timestamp ordering. Classifies direction as increasing, decreasing, or stable.

**OperationalSituation** — Assessment. Produced by `OperationalSituationAssessor`. Records a human-readable `assessment` string and references to the observations that informed it. Links to an `OperationalGoal`. Does not store the raw signal object.

**DecisionContext** — Planner snapshot. Produced by `create_decision_context`. Captures `goal_id`, `situation_id`, a copy of `assessment`, and `created_at`. Immutable record of what the planner knew.

**DecisionPlan** — Decision. Produced by `DecisionPlanner`. Contains `priority`, `recommendation`, `justification`, and `context_id`. Placeholder planning rules map assessment text to deterministic outputs.

**Action** — Record of what was done in response to a plan. Created by application components; persisted alongside other pipeline artifacts when repositories are configured.

**Outcome** — Measured consequence of an action. Created by application components; closed-loop learning based on outcomes remains future work.

### Executable scope today

The runnable pipeline spans **Observation** through **Outcome**. Demos and integration tests exercise this path. Closed-loop reasoning that feeds outcomes back into future decisions is deferred.

---

## 5. Deferred Decisions

The following were intentionally excluded from the initial architecture. Their absence is deliberate, not oversight.

| Deferred capability | Rationale |
|--------------------|-----------|
| **Persistence** | Repository interfaces define contracts; storage adapter choice deferred |
| **Telemetry ingestion** | Observations are constructed synthetically in tests and examples |
| **Machine learning** | Reasoning must remain deterministic and explainable |
| **Multi-signal reasoning** | Initial implementation uses one detector (`TrendDetector`); see [RFC-0002](RFC-0002-multi-signal-reasoning.md) |
| **Event dispatch** | Event contracts exist; no bus or handlers wired |
| **Closed-loop execution** | `Action` and `Outcome` entities defined; no execution or feedback path |

RFC-0002 extends this architecture by adding multiple independent signal detectors while preserving the principles documented here. It does not replace RFC-0001.

---

## 6. Consequences

### What this architecture enables

**Explainability.** Each stage has a named responsibility. A recommendation can be traced to a context, assessment, signal, and evidence chain.

**Replayability.** Immutable snapshots at each stage allow historical reasoning to be reconstructed from stored records without mutating prior state.

**Testability.** Components are independently specified — `TrendDetector` unit tests, pipeline integration tests, executable demos — without databases or external services.

**Incremental evolution.** New detectors, assessors, or planners can be introduced as replaceable application components. Domain entities remain stable.

**Independent reasoning components.** `TrendDetector` does not know about planning. `DecisionPlanner` does not re-detect trends. Boundaries are explicit.

### Trade-offs accepted

**More objects.** Each pipeline stage produces a distinct record. Verbosity is the cost of traceability.

**More explicit orchestration.** Callers wire components together. There is no framework, service container, or magic pipeline runner.

**Less convenience.** Simple scenarios require multiple steps. The architecture optimizes for clarity over brevity.

**Assessment as text.** `OperationalSituation.assessment` and `DecisionContext.assessment` are strings. Structured assessment types were deferred in favor of simplicity.

**Placeholder planning rules.** `DecisionPlanner` uses deterministic substring matching on assessment text. Production policy engines were explicitly out of scope.

---

## 7. Status

**Accepted.**

This architecture is implemented in `src/`, verified by `tests/`, demonstrated by `examples/`, and documented in `docs/architecture.md` and `docs/reasoning-pipeline.md`.

[RFC-0002](RFC-0002-multi-signal-reasoning.md) extends this foundation by evolving from single-signal to multi-signal reasoning. It preserves immutable entities, append-only history, layered architecture, and the evidence → signal → assessment → decision separation established here.

---

## References

- [README](../../README.md)
- [Architecture](../architecture.md)
- [Reasoning pipeline](../reasoning-pipeline.md)
- [CONTRIBUTING.md](../../CONTRIBUTING.md)
- [RFC-0002: Multi-Signal Reasoning](RFC-0002-multi-signal-reasoning.md)
