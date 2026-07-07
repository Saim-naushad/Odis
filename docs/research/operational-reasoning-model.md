# Operational Reasoning Model

## Purpose

ODIS separates **operational reasoning** from **domain knowledge**.

The framework provides deterministic reasoning mechanics — how observations are interpreted, assessed, and translated into decisions. **Operational profiles** provide engineering knowledge — which measurements matter, which relationships are significant, and what behavior is expected under given conditions.

This document explains the reasoning process independently of any industry. It describes the conceptual model that every ODIS profile follows, whether the asset is a fuel cell, a battery installation, a gas turbine, or a data center cooling loop. Profiles supply the knowledge; the framework supplies the reasoning structure.

**Core principle:** Operational reasoning is the process of transforming observations into justified operational decisions through explicit evidence and deterministic interpretation.

For repository layout, layer responsibilities, and component references, see [Architecture](../architecture.md) and [Reasoning pipeline](../reasoning-pipeline.md).

---

## 1. Why Operational Reasoning Exists

Industrial systems are monitored continuously. Temperature, pressure, flow, voltage, and dozens of other quantities arrive as streams of numbers. Conventional monitoring answers a narrow question: *did a value cross a threshold?*

That question is necessary but insufficient.

**Thresholds lose context.** A temperature of 85 °C may be normal under high load and abnormal under idle conditions. A fixed limit treats both cases identically.

**Alarms lack explanations.** An alarm states that a limit was breached. It does not explain whether the breach is consistent with current operating mode, whether related measurements corroborate the concern, or what operational state the system may be in.

**Multiple operating conditions can produce similar symptoms.** Rising temperature under increasing demand is expected. Rising temperature under stable demand is not. The same symptom — higher temperature — carries different operational meaning depending on context.

**Operators reason using context rather than isolated values.** Experienced operators do not react to a single reading. They compare measurements against one another, against expected behavior for the current mode, and against known failure patterns. They eliminate explanations that do not fit the evidence and retain those that remain consistent.

ODIS models this engineering reasoning process rather than alarm generation. The goal is not to produce more alerts. The goal is to produce **justified operational conclusions** — assessments and decisions that can be explained, audited, and extended.

---

## 2. The Operational Reasoning Pipeline

Every ODIS profile follows the same conceptual pipeline. Stages are ordered so that each step consumes the output of the previous one and adds a distinct kind of knowledge. No stage collapses into another.

```
Observations
    ↓
Evidence
    ↓
Expected Behavior
    ↓
Candidate Operational States
    ↓
Hypothesis Refinement
    ↓
Structured Assessment
    ↓
Planning
    ↓
Action
    ↓
Outcome
```

### Observations

Immutable facts recorded from the environment. Observations are the entry point: what was measured, on which asset, when, and in what units. They carry no interpretation.

### Evidence

Meaningful patterns and relationships that emerge when observations are viewed together. A single temperature reading is an observation; a rising temperature concurrent with rising pressure is evidence.

### Expected Behavior

What the system should exhibit given the current operational context. Expected behavior provides the reference against which observed evidence is judged. Behavior that aligns with expectation requires different treatment than behavior that diverges from it.

### Candidate Operational States

Plausible explanations for the observed evidence. Given a set of measurements and their relationships, multiple operational states may be consistent with the facts. At this stage, the reasoning engine enumerates possibilities rather than committing to a single diagnosis.

### Hypothesis Refinement

Deterministic elimination of explanations that contradict the evidence. Inconsistent candidates are removed. What remains is the smallest defensible set of operational states supported by the observations.

### Structured Assessment

A machine-readable summary of the reasoning outcome — trend direction, variation level, relationship facts, and other structured attributes derived from evidence and refinement. The assessment captures what the system believes about operational conditions at a point in time.

### Planning

Translation of assessment into a recommended course of action. Planning consumes assessments and planning-relevant facts, not raw observations. Every recommendation carries explicit justification traceable to the evidence that produced it.

### Action

A record of what was done in response to a plan. Actions close the loop between recommendation and execution, enabling accountability and later outcome measurement.

### Outcome

The measured consequence of an action. Outcomes allow future reasoning cycles to evaluate whether a prior decision had the intended effect without rewriting the original plan or action record.

This pipeline is conceptual. Individual stages map to existing framework types and components where implemented today; others describe the direction of the reasoning model as ODIS evolves. The ordering and separation of concerns remain stable across profiles and domains.

---

## 3. Observations

An observation is an **immutable fact** — a measurement recorded at a point in time.

Observations answer: *what was measured?* They do not answer: *what does it mean?*

**Observations are not conclusions.** A voltage reading of 42 V is a fact. "Stack degradation" is a conclusion that may later be supported by evidence spanning multiple observations.

**Observations contain no interpretation.** The domain model does not embed thresholds, health classifications, or alarm states on an observation. Interpretation belongs to later pipeline stages.

**Observations may be incomplete.** A reasoning cycle may receive only a subset of available measurements. Incomplete input does not prevent reasoning; it bounds what can be concluded. The system reasons from what is present, not from what is assumed.

**Observations become meaningful only when viewed together.** A coolant outlet temperature in isolation carries limited diagnostic value. The same reading, considered alongside inlet temperature, flow rate, and electrical load, becomes part of a coherent operational picture.

In ODIS, the domain entity `Observation` records these facts. When reasoning spans multiple measurement types on the same asset, observations are grouped for joint analysis. `ObservationGroup` collects observations that share an asset identity and exposes them through a measurement index, enabling detectors and analyzers to access temperature, pressure, flow, and other channels without changing the shape of the observation record itself.

Observations are append-only. A revised understanding of conditions does not mutate prior observations; it produces new assessments, contexts, and plans.

---

## 4. Evidence

Evidence emerges from **relationships between observations**.

A lone measurement rarely justifies an operational conclusion. Operators and engineers reason by comparing quantities — checking whether subsystem responses remain mutually consistent under a given operating condition.

Representative relationship patterns include:

| Relationship | What it reveals |
|---|---|
| Temperature + pressure | Whether thermal and fluid subsystems are responding coherently |
| Voltage + current | Whether electrical performance aligns with generation level |
| Flow + demand | Whether supply is tracking load |

Evidence is not a single observation and not yet an assessment. It is the structured result of analyzing how observations relate to one another — trends, correlations, contradictions, and other deterministic patterns detected across measurement types.

Isolated measurements answer *what is the value?* Evidence answers *how do these values relate?*

In ODIS, cross-measurement evidence is aggregated in `RelationshipAnalysis` — an immutable result produced by composing relationship detectors according to a profile's relationship policy. Correlation describes an observed relationship between measurements. Contradiction flags predefined combinations that appear operationally inconsistent and deserve additional review in context. Neither is a final diagnosis; both are evidence inputs to later stages.

Relationship policies, defined by operational profiles, determine **which** relationships are evaluated. Detectors determine **how** those relationships are evaluated. This separation keeps domain knowledge configurable without embedding equipment-specific assumptions into the reasoning framework.

---

## 5. Expectations

Expectation-based reasoning asks a question that threshold monitoring cannot: *is this behavior expected given current conditions?*

Expected behavior depends on operational context. The same measurement change can be normal in one mode and concerning in another.

**Higher load → higher temperature → expected**

Under increasing electrical demand, rising temperature is a coherent subsystem response. No investigation is warranted unless the magnitude diverges from established patterns.

**Stable load → higher temperature → unexpected**

Under constant demand, rising temperature suggests a change in thermal performance, cooling effectiveness, or an unmodeled disturbance. The symptom is identical; the operational meaning is not.

ODIS compares observed behavior against expected behavior **before** producing assessments. A rising trend is not automatically elevated to a high-priority concern. It is evaluated in context: does the observed pattern match what the current operating mode predicts?

Future operational profiles may define explicit `ExpectationPolicy` objects — declarative rules that state what behavior is anticipated under named operating conditions. Such policies do not exist in the framework today. The conceptual model accommodates them as a natural extension: profiles supply expectations; the reasoning pipeline evaluates evidence against those expectations.

Expectations do not replace evidence. They provide the reference frame that makes evidence interpretable.

---

## 6. Hypothesis Refinement

Once evidence is established and evaluated against expectations, the reasoning process considers **candidate operational states** — plausible explanations for what the system may be experiencing.

Hypothesis refinement is deterministic elimination:

```
Observations
    ↓
Possible explanations
    ↓
Remove inconsistent explanations
    ↓
Remaining operational state
```

Each candidate state is an operational hypothesis: a named condition that, if true, would account for the observed evidence. Candidates are drawn from profile knowledge — engineering principles about how subsystems interact, which symptom profiles correspond to which fault classes, and which combinations of measurements are diagnostically significant.

Refinement removes candidates that contradict the evidence. If temperature is rising but pressure is stable and load is constant, explanations that require a supply restriction may be eliminated. If voltage is declining while current is stable, explanations consistent with performance loss remain.

**Multiple explanations may remain valid.** ODIS does not force a single diagnosis when the evidence supports more than one consistent state. Retaining multiple valid hypotheses is honest engineering practice: the system reports what the evidence supports, not what a scoring model prefers.

ODIS favors explainable deterministic reasoning over statistical inference in this stage. Every elimination step is governed by explicit rules that can be inspected, tested, and replayed. The design philosophy is transparency: an operator or engineer should be able to follow the chain from observation to remaining hypothesis without consulting a model whose internals are opaque.

This is a design choice suited to operational environments where auditability and reproducibility matter. It is not a claim that deterministic reasoning is universally superior — only that it aligns with how operational teams evaluate evidence and justify decisions.

---

## 7. Structured Assessment

Assessments occur **late** in the pipeline, after evidence has been assembled, expectations evaluated, and hypotheses refined.

An assessment summarizes what the reasoning process concluded about operational conditions. It is distinct from the inputs that produced it:

**Assessments are not raw sensor values.** A temperature of 78 °C is an observation. "Increasing operational stress with cross-measurement contradictions detected" is an assessment.

**Assessments are not alarms.** An alarm fires on a rule breach. An assessment explains operational meaning — what the evidence supports, how it compares to expectation, and what hypotheses remain after refinement.

**Assessments summarize remaining evidence.** The human-readable assessment text on `OperationalSituation` communicates the conclusion in operator-facing language. The machine-readable `StructuredAssessment` captures the same evidence in typed attributes — trend direction, variation level, and whether cross-measurement correlations or contradictions were detected.

`StructuredAssessment` adds no new reasoning beyond what the assessor already derived. It exists so that planners, analytics, and future components can consume operational conclusions without parsing natural language. The assessment is a snapshot: immutable once created, replaced by a new record when understanding changes.

---

## 8. Planning

Planning translates assessment into action. It operates on conclusions, not on raw telemetry.

The planning boundary is deliberate. A planner should not re-derive trends, re-evaluate relationships, or reinterpret observations. Those responsibilities belong to earlier stages. Planning answers: *given what we now believe about operational conditions, what should be done?*

In ODIS, the planning path flows through:

**`PlanningContext`** — planning-relevant facts derived from `StructuredAssessment`. Today this includes whether cross-measurement relationships or contradictions were detected. It intentionally excludes priorities, recommendations, and policy logic.

**`DecisionPlanner`** — produces a `DecisionPlan` from a `DecisionContext` (a frozen snapshot of goal, situation, and assessment) and an optional `PlanningContext`. The planner currently applies placeholder rules; the dependency injection point exists so future planning policies can evolve without changing assessment behavior.

**`Action`** — records what was done in response to a plan.

**`Outcome`** — records the measured consequence of an action.

Traceability is essential. Every decision must be explainable in terms of the assessment and evidence that produced it. An engineer reviewing a plan should be able to walk backward through the chain — from recommendation to assessment to structured evidence to observations — without gaps in the reasoning record.

---

## 9. Deterministic Reasoning

ODIS favors deterministic reasoning throughout the operational pipeline.

**Repeatability.** The same observations, processed through the same profile, produce the same conclusions. Reasoning does not depend on stochastic sampling, model drift, or non-reproducible inference.

**Auditability.** Every stage produces an immutable record. Assessments, contexts, and plans can be replayed from stored artifacts. An operator can answer what the system believed at a specific point in time.

**Engineering transparency.** Rules are explicit. Relationship detectors apply defined comparisons. Hypothesis refinement follows stated elimination logic. There is no hidden layer between evidence and conclusion.

**Reproducibility.** Tests, demos, and production runs can verify reasoning behavior deterministically. A failure can be reproduced from inputs without ambiguity about which code path or model version was involved.

Deterministic systems are not universally superior. They are not the right tool for every class of problem. ODIS adopts deterministic reasoning because operational environments demand conclusions that can be explained to regulators, investigated by engineers, and defended in post-incident review. When a recommendation affects physical equipment or personnel safety, the reasoning behind it must be inspectable.

---

## 10. Relationship to Operational Profiles

ODIS architecture separates two responsibilities:

```
Framework  →  Reasoning
Profiles   →  Knowledge
```

The framework defines **how** reasoning proceeds: observation grouping, relationship analysis, assessment structure, planning boundaries, and execution metadata. Profiles define **what** is known about a domain: which measurement relationships matter, which contradictions are worth flagging, what operating modes exist, and what behavior is expected under each.

| Domain | Profile supplies |
|---|---|
| Fuel cells | Reactant delivery relationships, thermal–electrical coupling, hydration fault patterns |
| Battery systems | State-of-charge dynamics, cell imbalance indicators, thermal runaway precursors |
| Gas turbines | Compressor–turbine coherence, exhaust temperature profiles, vibration signatures |
| Industrial cooling | Chiller efficiency relationships, refrigerant pressure–temperature coherence |
| Data centers | Rack thermal distribution, airflow–load coupling, redundancy state |
| Future domains | Whatever engineering knowledge the profile author documents |

All profiles share one reasoning model. A fuel cell profile and a data center profile traverse the same pipeline stages in the same order. They differ only in the knowledge they inject — relationship policies today, expectation and planning policies as the framework matures.

This separation is what makes ODIS generalizable. Adding a new industry does not require rewriting detectors, assessors, or planners. It requires authoring a profile that packages domain-specific operational knowledge and connecting it to the existing reasoning engine.

---

## 11. Long-Term Vision

The conceptual pipeline described in this document exceeds what any single profile implements today. The following directions represent possible future architectural extensions — not current capabilities.

**ExpectationPolicy.** Declarative rules that define expected behavior under named operating conditions, enabling explicit comparison between observed and anticipated patterns.

**Relationship graphs.** Richer representations of how measurements and subsystems relate, beyond pairwise correlation and contradiction detection.

**Scenario reasoning.** Profile-scoped policies for distinct operating modes — start-up, steady-state, shutdown, emergency — each with its own expectation and assessment context.

**Operator knowledge libraries.** Structured repositories of engineering principles that profiles reference, keeping domain knowledge documented, versioned, and traceable to assessment rules.

**Planning policies.** Domain-specific decision rules that consume `PlanningContext` facts to produce recommendations aligned with operational practice.

**Domain packs.** Bundled profiles, knowledge documents, relationship policies, and example scenarios packaged for a specific industry vertical.

**Timeline reasoning.** Analysis across multiple reasoning cycles — tracking whether operational conditions are improving, stable, or worsening over time, complementing per-cycle assessment.

These are architectural directions, not commitments. Each should be introduced only when it strengthens traceability and explainability without collapsing the separation between reasoning and knowledge.

---

## Guiding Principles

The operational reasoning model rests on a small set of principles that govern design decisions across the framework:

- **Observations before conclusions.** Reasoning begins with facts, not interpretations.
- **Evidence before assessment.** Measurements gain operational meaning through relationships, not in isolation.
- **Expectations before diagnosis.** Observed behavior is judged against what the current context predicts.
- **Assessment before planning.** Decisions consume conclusions, not raw telemetry.
- **Decisions must be explainable.** Every recommendation carries justification traceable to evidence.
- **Every conclusion should be traceable.** The full chain from observation to outcome is inspectable and replayable.

---

## Related documentation

- [Architecture](../architecture.md) — layer structure, operational profiles, and component reference
- [Reasoning pipeline](../reasoning-pipeline.md) — stage-by-stage flow from observation to outcome
- [RFC-0001: Core Operational Reasoning Architecture](../rfcs/RFC-0001-core-operational-reasoning-architecture.md) — foundational design decisions
- [Fuel Cell Operational Knowledge](fuel-cell-operational-knowledge.md) — example domain knowledge document for a specific profile
