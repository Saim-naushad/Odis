# RFC-0002: Multi-Signal Reasoning

| Field | Value |
|-------|-------|
| Status | Proposed |
| Date | 2026-06-26 |
| Depends on | RFC-0001 (Architectural Foundation) |
| Related | [reasoning-pipeline.md](../reasoning-pipeline.md), [architecture.md](../architecture.md) |

## Summary

This RFC defines how ODIS evolves from single-signal to multi-signal operational reasoning. It preserves the principles established in RFC-0001 — immutable domain records, append-only history, explicit layering, and separation of evidence, signal, assessment, and decision — while allowing multiple independent detectors to inform a single operational assessment.

This document proposes architecture only. No implementation is included.

---

## 1. Problem Statement

### Single-signal reasoning is incomplete

Today, ODIS derives one signal from a sequence of observations:

```
Observations → TrendDetector → DetectedTrend → OperationalSituationAssessor → OperationalSituation
```

`TrendDetector` answers one question: what is the overall direction from the first to the last value (after timestamp ordering)? That is a useful but narrow view of operational conditions.

A single signal cannot fully describe operational reality because:

- **Different phenomena require different detectors.** Direction, variability, rate-of-change, and threshold proximity are distinct questions. Conflating them into one detector produces opaque or brittle logic.
- **Signals can disagree.** A sequence may be directionally stable while highly variable. Treating one signal as authoritative hides conflicts that operators would notice immediately.
- **Assessment requires synthesis.** Operational meaning emerges from interpreting multiple signals in context — not from any single measurement-derived classification.

### Motivating example: oscillating operations

The `examples/oscillating_operations_demo.py` walkthrough demonstrates this limitation deliberately.

Flow rate readings:

```
100 → 150 → 80 → 160 → 70 → 100
```

`TrendDetector` classifies this sequence as **stable** because the first and last values are equal. The pipeline then produces:

- Assessment: *"Operational conditions stable"*
- Recommendation: *"Continue monitoring"*

A human operator would recognize **high instability** despite neutral overall direction. The architecture propagates the signal faithfully; the signal itself is insufficient.

This is not a defect in layering. It is evidence that **one signal type cannot represent operational conditions alone**.

### Observations, signals, and assessments

These concepts must remain distinct:

| Concept | Definition | Example today |
|---------|------------|---------------|
| **Observation** | Immutable evidence — a recorded measurement | `Observation(value=150.0, unit="m3/h", ...)` |
| **Signal** | Deterministic pattern extracted from observations | `DetectedTrend(direction=STABLE, ...)` |
| **Assessment** | Operational interpretation of evidence informed by signals | `OperationalSituation(assessment="Operational conditions stable", ...)` |

Observations do not interpret themselves. Signals do not recommend actions. Assessments do not re-detect patterns. Multi-signal reasoning adds more signal inputs; it does not collapse these boundaries.

---

## 2. Design Goals

Multi-signal reasoning must:

1. **Support multiple independent signal detectors** running against the same observation sequence without coupling detectors to each other.
2. **Preserve the immutable domain model** — new signals introduce new value objects, not mutable state on existing entities.
3. **Preserve append-only history** — revised interpretations remain new `OperationalSituation` records.
4. **Keep detectors independently testable** — each detector has its own behavioral specification, as `TrendDetector` does today.
5. **Allow new detectors without modifying existing detectors** — `VariationDetector` must not require changes to `TrendDetector`.
6. **Keep reasoning explainable** — every assessment must be traceable to the signals and evidence that produced it.
7. **Preserve current layering** — detectors and assessors remain in the application layer; domain entities do not perform detection.

---

## 3. Architectural Principle

Detectors independently interpret evidence and produce typed detector results (e.g., `DetectedTrend`, `DetectedVariation`). Each detector answers one narrowly scoped question about an observation sequence. Detectors must not coordinate with one another, produce recommendations, or embed operational policy.

`OperationalSituationAssessor` is the only component responsible for combining detector outputs into an operational assessment. Signal synthesis — including resolution of conflicting signals — belongs here, not in detectors or a separate fusion layer at this stage.

Observations remain the primary evidence source. The assessor must continue to receive observations alongside detector outputs so that every assessment remains grounded in raw evidence, not derived signals alone. Signals inform interpretation; they do not replace the underlying measurements.

---

## 4. Non-Goals

This RFC does **not** introduce:

- Machine learning or probabilistic models
- Confidence scores or uncertainty propagation (deferred; see Open Questions)
- Changes to the domain event contracts or an event bus
- Persistence or repository implementations
- Plugin systems, runtime detector discovery, or dynamic registration
- Changes to `DecisionPlanner` behavior in the initial migration
- Multi-asset or cross-measurement reasoning in the first implementation

---

## 5. Design Alternatives

Three approaches are evaluated. None is assumed correct without analysis.

### Option A: Pass multiple detector outputs directly into the assessor

**Description**

Each detector produces its own typed result (e.g., `DetectedTrend`, `DetectedVariation`). `OperationalSituationAssessor` accepts multiple signal inputs alongside observations and the goal, and applies deterministic rules to produce an assessment.

```
Observations ──┬── TrendDetector ────── DetectedTrend ──┐
               │                                        ├── Assessor → OperationalSituation
               └── VariationDetector ─ DetectedVariation ┘
```

**Advantages**

- Minimal new structure — extends the existing assessor pattern directly.
- Explicit data flow — a reader can see exactly which signals inform an assessment.
- Each signal retains its own type and test contract.
- No new pipeline stage to document, test, or maintain.

**Disadvantages**

- Assessor parameter list grows as signals are added.
- Signal composition logic lives inside the assessor unless extracted later.
- Potential for assessor complexity if many signals and conflict rules accumulate.

**Alignment with ODIS philosophy**

Strong. Matches replaceable application components, explicit reasoning, and avoidance of abstraction until patterns repeat.

---

### Option B: Introduce a generic `Signal` abstraction

**Description**

All detectors implement a common interface or inherit from a shared `Signal` type. The assessor consumes a collection of `Signal` instances rather than typed results.

```python
# Illustrative — not proposed implementation
class Signal(Protocol):
    signal_type: str
    asset_id: str
    ...

signals: tuple[Signal, ...] = (trend_detector.detect(...), variation_detector.detect(...))
assessor.assess(goal, observations, signals)
```

**Advantages**

- Uniform consumption model as detector count grows.
- Assessor signature remains stable (`signals: Sequence[Signal]`).
- Conceptually tidy — "signals in, assessment out."

**Disadvantages**

- Risks erasing signal-specific semantics behind a generic interface.
- Encourages lowest-common-denominator fields (`signal_type: str`) that weaken type safety.
- Premature abstraction — ODIS currently has one signal; generalization precedes demonstrated repetition.
- MyPy and test specifications become less precise.

**Alignment with ODIS philosophy**

Weak today. RFC-0001 explicitly cautions against complexity before repeated patterns justify it. A protocol may become appropriate after three or more detectors share genuine structural commonality.

---

### Option C: Introduce a dedicated signal fusion stage

**Description**

A new application component sits between detectors and the assessor. It accepts multiple detector outputs and produces a fused signal summary (e.g., `FusedSignals` or `SignalProfile`) that the assessor consumes.

```
Observations → Detectors → SignalFusion → FusedSignals → Assessor → OperationalSituation
```

**Advantages**

- Separates "what was detected" from "how signals combine."
- Assessor focuses purely on operational interpretation.
- Natural home for conflict-resolution policy as complexity grows.

**Disadvantages**

- Adds a pipeline stage that does not exist today for a single signal.
- "Fusion" semantics are assessment policy in disguise — the stage may duplicate assessor responsibilities.
- Harder for contributors to trace reasoning across an extra component.
- Empty or pass-through fusion is boilerplate until conflict rules are genuinely complex.

**Alignment with ODIS philosophy**

Mixed. Clean separation is appealing, but the fusion stage is justified only when composition rules are non-trivial and shared across multiple assessors. Neither condition is met today.

---

## 6. Recommended Direction

**Recommend Option A: pass multiple typed detector outputs directly into `OperationalSituationAssessor`.**

### Justification

Option A is the smallest change that solves the oscillating scenario without introducing new architectural concepts:

- **Explicit reasoning.** Each signal type remains visible at the assessor boundary. An assessment can be explained as "stable trend + high variation → unstable conditions."
- **Simple architecture.** No fusion stage, no protocol hierarchy, no registry. Two detectors, two typed inputs, one assessor.
- **Replaceable components.** Detectors remain independent classes with independent tests. The assessor's composition rules can evolve or be replaced without touching detectors.
- **Avoids premature abstraction.** Option B generalizes before the second detector exists. Option C adds a stage before composition complexity warrants it.

### Why not a fusion stage today

With two deterministic signals, fusion is a small set of conditional rules — the same complexity class as assessment itself. Extracting `SignalFusion` now would create a component whose sole job is forwarding typed results or duplicating assessor logic. If assessor composition grows unwieldy after three or more signals, a fusion or policy component can be extracted in a future RFC without breaking the domain model.

### Typed results, not a generic `Signal`

Each detector should continue to return a dedicated value object:

| Detector | Result type (proposed) |
|----------|------------------------|
| `TrendDetector` | `DetectedTrend` (exists) |
| `VariationDetector` | `DetectedVariation` (new) |

The assessor accepts named, typed parameters — not a heterogeneous collection. This preserves MyPy enforcement and clear test specifications.

---

## 7. Migration Plan

The migration is incremental. Each step leaves the pipeline executable and tests green.

### Step 1: Introduce `VariationDetector`

- Add `DetectedVariation` value object in `domain/value_objects/` (e.g., `level: VariationLevel` with values such as `LOW`, `HIGH`).
- Add `VariationDetector` in `application/` with deterministic logic (e.g., range or standard deviation threshold-free comparison of spread relative to mean — exact algorithm deferred to implementation PR).
- Add unit tests specifying the detector contract, including the oscillating sequence.

`TrendDetector` remains unchanged.

### Step 2: Update `OperationalSituationAssessor`

- Extend `assess()` to accept `DetectedVariation` alongside `DetectedTrend`.
- Update assessment rules deterministically. Example policy for the oscillating case:

  | Trend | Variation | Assessment (illustrative) |
  |-------|-----------|----------------------------|
  | STABLE | HIGH | *"Operational instability detected"* |
  | INCREASING | LOW | *"Increasing operational stress detected"* (existing) |
  | ... | ... | ... |

- Validate that all signals reference the same `asset_id` and `measurement_type` as observations.

`OperationalSituation` entity shape remains unchanged — assessment is still a `str`. Signal details are not persisted on the situation in this migration; they informed the assessment at creation time.

### Step 3: Update demos

- `oscillating_operations_demo.py` should run both detectors and produce an instability-aware assessment.
- `run_demo.py` summary should note multi-signal reasoning where appropriate.
- Heatwave and stable demos gain `VariationDetector` calls but should produce equivalent assessments if variation is low.

### Step 4: Update tests

- Extend builders if needed (no change to `build_observation_sequence` required).
- Add `VariationDetector` unit tests in `tests/application/`.
- Add or update integration test for oscillating scenario expecting non-stable assessment.
- Keep existing `TrendDetector` tests unchanged.

### Step 5: Keep planner unchanged initially

`DecisionPlanner` continues to consume `DecisionContext.assessment` via substring matching. New assessment phrases (e.g., containing *"instability"*) require corresponding placeholder rules in a follow-up PR if planner output should change for unstable conditions.

`create_decision_context` continues to snapshot assessment text — no structural change.

### Backward compatibility

- Existing single-signal call sites can be updated to pass both signals; there is no runtime detector registry to migrate.
- Domain entities, events, and repository interfaces are unaffected.
- Append-only semantics are preserved.

---

## 8. Open Questions

The following topics are intentionally unresolved. They are not blockers for the initial `VariationDetector` migration.

### Confidence propagation

Should individual signals carry confidence metadata? ODIS currently avoids probabilistic reasoning. If confidence is introduced, it likely belongs on signal value objects — but the semantics are undefined.

### Signal conflicts

When signals imply contradictory operational states (e.g., increasing trend + high variation decreasing), what precedence rules apply? Option A places this in the assessor today; a dedicated policy component may emerge later.

### Detector ordering

Detectors are independent and order should not matter. If future detectors depend on outputs of prior detectors, the architecture must be revisited. This RFC assumes **parallel, independent detectors** over the same observation sequence.

### Multi-asset assessments

Today, all observations in a reasoning pass belong to one asset and one measurement type. Situations spanning multiple assets are out of scope.

### Signal persistence

Should signals be recorded alongside situations for replay? Today only `assessment` and `observation_ids` are stored on `OperationalSituation`. Recording signal snapshots on `DecisionContext` (as assessment is today) is a future option.

### Planner coupling

Placeholder planner rules match assessment substrings. Multi-signal assessments increase the vocabulary of assessment strings. A future RFC may introduce structured assessment types or planner inputs decoupled from free text.

---

## References

- [Architecture](../architecture.md) — layer responsibilities and design principles
- [Reasoning pipeline](../reasoning-pipeline.md) — current pipeline and extension sketch
- [CONTRIBUTING.md](../../CONTRIBUTING.md) — contribution philosophy
- `examples/oscillating_operations_demo.py` — motivating limitation walkthrough
