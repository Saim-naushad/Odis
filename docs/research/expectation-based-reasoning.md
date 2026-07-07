# Expectation-Based Reasoning

## Purpose

Industrial operators do not monitor equipment by asking whether individual values exceed limits. They ask whether the system is behaving as it should under current conditions. That question — *is this what I expect right now?* — is the foundation of operational reasoning in ODIS.

**Expectations are fundamental to operational reasoning** because physical systems are coupled. A temperature rise may be the correct thermal response to increased load, a sign of cooling degradation, or an artifact of sensor placement. The raw measurement is identical in each case. What changes is whether the observation fits the operational context. Expectations supply that context: they describe how variables ought to behave when subsystems are working together under a given mode of operation.

**Operators compare observed behavior against expected behavior.** Experienced judgment follows a consistent pattern. Measurements are collected, relationships among them are noted, and the resulting pattern is compared against what the current operating mode predicts. When the pattern aligns, the operator concludes that subsystems are responding coherently. When it diverges, the same measurements become diagnostically significant. Expectation-based reasoning models this comparison explicitly rather than treating every deviation as an alarm.

**This differs fundamentally from threshold monitoring.** Threshold monitoring asks a single question: *did a value cross a limit?* That question is context-free. A fixed temperature limit treats idle and full-load operation identically. It cannot distinguish expected thermal response from unexpected thermal stress. It cannot explain why a reading matters. Expectation-based reasoning asks a richer question: *given what the system is doing, is this behavior coherent?* The answer depends on load, mode, ambient conditions, and the relationships among measurements — not on a static boundary.

This document defines the concept of expectation-based reasoning within ODIS. It answers the conceptual questions that will guide future implementation. It does not describe implementation details, introduce APIs, or modify existing architecture. For the broader reasoning pipeline, see [Operational Reasoning Model](operational-reasoning-model.md). For repository structure and layer responsibilities, see [Architecture](../architecture.md).

---

## 1. What is an Expectation?

An **expectation** is a qualitative description of how one or more operational variables are expected to behave under a particular operational context.

Expectations are not numeric limits. They are engineering statements about coherent subsystem response. They describe directional behavior, coupling, and consistency — not alarm thresholds.

**Expectations are contextual.** The same variable may be expected to rise, fall, or remain stable depending on operating mode. Stack temperature is expected to increase when electrical load increases during normal load-following. The same temperature increase under constant load is not expected and carries different operational meaning. Context — current demand, ambient conditions, operating phase — determines which expectation applies.

**Expectations are deterministic.** Given a defined operational context and a set of observed relationships, evaluating an expectation produces a consistent result. The same evidence, evaluated against the same expectation, always yields the same judgment: expected, unexpected, or indeterminate when context is insufficient. Expectations do not depend on probabilistic inference or model sampling. They reflect explicit engineering knowledge that can be inspected, tested, and replayed.

**Expectations are domain knowledge.** They encode how equipment behaves according to physics, control design, and operational practice. A fuel cell operator expects cooling demand to track electrical load. A battery operator expects cell voltages to remain balanced during steady discharge. A gas turbine operator expects exhaust temperature to correlate with fuel flow during steady-state operation. These are not universal truths of the reasoning framework. They are principles specific to each equipment domain, authored and maintained within operational profiles.

An expectation might be stated as:

> Under increasing electrical load, stack temperature is expected to rise as waste heat generation increases.

This statement says nothing about a maximum temperature. It says how temperature ought to respond relative to load in a particular context. That qualitative, relational character is what distinguishes an expectation from a threshold or a raw measurement.

---

## 2. Expectations vs Relationships

Relationships and expectations are related but distinct concepts. Confusing them weakens operational reasoning: a system that knows variables are connected but not how they should behave under current conditions cannot judge whether observed patterns are coherent.

### Relationship

A **relationship** describes that variables are connected. It states that measurements influence, correlate with, or constrain one another — without specifying what should happen in a given context.

| Relationship | What it states |
|---|---|
| Current ↔ voltage | Electrical load and stack voltage are physically coupled through polarization behavior. |
| Temperature ↔ pressure | Thermal and fluid subsystems interact within the balance of plant. |
| Fuel flow ↔ current | Fuel delivery and electrical demand are coordinated in normal operation. |

A relationship answers: *are these variables linked?* It does not answer: *given current conditions, is the way they are behaving correct?*

### Expectation

An **expectation** describes how connected variables should behave under a given context. It builds on relationships but adds operational judgment.

| Expectation | What it states |
|---|---|
| Under increasing load, voltage is expected to decline gradually. | The current–voltage relationship should manifest as a modest, continuous voltage decrease — not a sudden collapse. |
| Under increasing load, coolant outlet temperature is expected to rise. | The thermal–electrical coupling should produce higher heat rejection as generation increases. |
| Under increasing load, fuel flow is expected to track current demand. | The fuel–current relationship should appear as coordinated, proportional response — not a sustained lag. |

### Why the distinction matters

Evidence detection identifies relationships: temperature is rising while pressure is stable; voltage is declining while current is increasing. These are observed patterns — facts about how measurements relate at a point in time.

Expectation evaluation interprets those patterns: given that load is increasing, is rising temperature expected? Given that load is stable, is declining voltage expected? The relationship is the same in both cases; the expectation differs because the context differs.

A reasoning system that stops at relationships can report correlations and contradictions. A reasoning system that evaluates expectations can distinguish normal coupled response from abnormal decoupling. Relationships supply evidence. Expectations supply the reference frame that makes evidence operationally meaningful.

---

## 3. Expectations vs Thresholds

Threshold monitoring and expectation-based reasoning address different questions. Understanding the difference clarifies why ODIS treats expectations as a distinct reasoning layer rather than an extension of alarm logic.

### Threshold monitoring

A threshold states a boundary on a single variable:

> Temperature > 80 °C

This rule is context-free. It fires whenever the value exceeds the limit, regardless of operating mode, load level, or the behavior of related measurements. It answers: *is this value too high?* It does not answer: *why is it high, and should it be high right now?*

Thresholds are necessary for safety envelopes and regulatory limits. They are insufficient for operational reasoning because they discard the information operators use to judge significance.

### Expectation-based reasoning

An expectation states how variables should behave relative to one another under a defined context:

> Temperature increased because load increased.

This statement is relational and contextual. It asserts that, in the current operating mode, a temperature rise is the expected thermal response to higher electrical demand. The same temperature rise without a corresponding load increase would violate the expectation — even if the absolute temperature remains below 80 °C.

| Aspect | Threshold | Expectation |
|---|---|---|
| Question asked | Did a value cross a limit? | Is this behavior coherent given current conditions? |
| Scope | Single variable | One or more variables in context |
| Context dependence | None | Essential |
| Output | Alarm or no alarm | Expected, unexpected, or indeterminate |
| Explanatory power | States that a limit was breached | States whether behavior fits operational understanding |

### Context dependence

Context dependence is the central difference. Consider the same temperature reading — 78 °C — in two scenarios:

**Scenario A: Full load, ambient 35 °C**

The system is operating at high electrical demand in hot weather. Cooling systems are working hard. An experienced operator expects elevated stack temperature. The reading is consistent with context. A threshold at 75 °C would alarm; an expectation evaluation would not elevate concern.

**Scenario B: Idle, ambient 20 °C**

The system is at minimal load in moderate weather. Cooling demand should be low. A temperature of 78 °C is not consistent with the expected thermal state. A threshold at 80 °C would not alarm; an expectation evaluation would flag the divergence.

Neither scenario is resolved by the absolute value alone. Both require context — load, ambient conditions, the behavior of related measurements — to determine operational meaning. Expectations encode that context. Thresholds do not.

---

## 4. Expectations and Evidence

Evidence describes observed relationships among measurements. Expectations determine whether those relationships are operationally significant. Without expectations, evidence is descriptive. With expectations, evidence gains operational meaning.

The evaluation flow follows a simple structure:

```
Observed behavior
        ↓
    Expected?
        ↓
Evidence gains operational meaning
```

### Observed behavior

Cross-measurement analysis produces evidence: trends, correlations, contradictions, and other deterministic patterns detected across observation types. At this stage, the reasoning system knows *what happened* — temperature rose, pressure remained stable, load increased — but not yet whether that pattern matters.

### Expected?

The evidence is compared against expectations defined for the current operational context. The comparison is qualitative and deterministic:

- **Expected:** The observed pattern matches what the current context predicts. The evidence is noted but does not, by itself, warrant elevated concern.
- **Unexpected:** The observed pattern diverges from what the current context predicts. The evidence becomes diagnostically significant.
- **Indeterminate:** The operational context is insufficient to select an expectation, or required measurements are absent. The system reports what it can without over-interpreting.

### Evidence gains operational meaning

The result transforms descriptive evidence into operational evidence. "Temperature is rising" is a trend. "Temperature is rising while load is stable — unexpected under current conditions" is operational evidence. The measurements are identical. The expectation supplies the interpretation.

This enrichment happens before assessment and diagnosis. Expectations do not replace evidence detection. They provide the reference against which detected patterns are judged. A rising temperature concurrent with rising load is evidence of thermal–electrical coupling; evaluated against the expectation for load-following operation, it confirms coherent subsystem response. The same rising temperature with stable load is the same kind of evidence; evaluated against a different expectation, it signals potential thermal management concern.

Expectations make evidence actionable without converting every pattern into an alarm. Expected behavior is recorded and traceable. Unexpected behavior is flagged for further reasoning. The distinction mirrors how operators prioritize attention: not every change requires investigation, but unexpected changes in context always deserve scrutiny.

---

## 5. Expectations and Operational Profiles

Expectations belong in **domain profiles**, not in the reasoning framework itself. This separation follows the same principle that governs relationships, planning rules, and assessment knowledge throughout ODIS: the framework defines how reasoning proceeds; profiles define what is known about a domain.

The framework provides the structure for evaluating expectations — a place in the reasoning pipeline where observed evidence is compared against a reference. Profiles supply the expectations themselves: the engineering knowledge about how equipment should behave under named operating conditions.

Embedding domain-specific expectations in the framework would couple reasoning mechanics to equipment knowledge. A fuel cell thermal expectation does not apply to a battery installation. A gas turbine compressor expectation does not apply to a data center cooling loop. Generalizing expectations into the framework would either dilute them into useless abstractions or hard-code domain assumptions that belong in profiles.

### Fuel cells

A PEM fuel cell profile encodes expectations drawn from electrochemical and thermal engineering:

- Under increasing electrical load, stack temperature is expected to rise as waste heat increases.
- Under increasing load, fuel flow and air flow are expected to track current demand.
- Under steady load, stack voltage is expected to remain relatively stable; a sustained decline suggests performance loss.
- During normal operation, coolant outlet temperature is expected to exceed inlet temperature as heat is rejected.

These expectations do not specify numeric limits. They describe coherent subsystem response for a fuel cell installation. They are documented in [Fuel Cell Operational Knowledge](fuel-cell-operational-knowledge.md) and expressed through the fuel cell operational profile.

### Batteries

A battery system profile encodes expectations drawn from electrochemical storage behavior:

- During discharge, state of charge is expected to decrease monotonically.
- Under balanced operation, cell voltages are expected to remain within a narrow spread.
- Under increasing discharge current, terminal voltage is expected to decline gradually due to internal resistance.
- During charging, temperature is expected to rise modestly; a rapid rise under moderate charge rate is unexpected.

Each expectation is specific to battery chemistry, pack configuration, and operating practice. They belong in a battery profile, not in the framework.

### Gas turbines

A gas turbine profile encodes expectations drawn from turbomachinery and combustion engineering:

- During load increases, fuel flow and exhaust temperature are expected to rise together.
- Under steady-state operation, compressor discharge pressure and turbine inlet temperature are expected to maintain a stable relationship.
- During normal operation, vibration levels are expected to correlate with rotational speed and load.
- After a load change, transient parameters are expected to settle within a characteristic time; prolonged oscillation is unexpected.

These expectations reflect gas path physics and control design. They are domain knowledge authored for a gas turbine profile.

### The profile boundary

Profiles may organize expectations by operating scenario — start-up, steady-state, shutdown, emergency — as domain knowledge matures. The framework does not prescribe how expectations are structured within a profile. It prescribes that expectations are evaluated at the appropriate stage of the reasoning pipeline and that the evaluation is deterministic and traceable.

This boundary keeps ODIS generalizable. Adding expectations for a new equipment type does not require framework changes. It requires authoring or extending an operational profile with the engineering knowledge that domain demands.

---

## 6. Future Directions

The following ideas represent possible future directions for expectation-based reasoning in ODIS. They are **conceptual only** — design explorations that may inform implementation when the reasoning model matures. None are current capabilities, commitments, or architectural changes.

### ExpectationPolicy

A profile-scoped policy that declares which expectations apply under named operating conditions. Conceptually, an ExpectationPolicy would allow a profile author to state: under load-following operation, these behavioral expectations are active; under idle, a different set applies. The policy would separate *which* expectations are relevant from *how* the framework evaluates them — mirroring the existing separation between relationship policies and relationship detectors.

### Expectation graphs

Richer representations of how expectations relate to one another and to subsystem structure. Where today's model evaluates expectations individually or in small groups, an expectation graph could represent dependencies: if load is increasing, thermal and fuel expectations are jointly active; if a cooling fault is suspected, thermal expectations take precedence over efficiency expectations. This remains a knowledge representation question for profiles, not a framework abstraction.

### Operating scenarios

Explicit scenario definitions that bundle context, active expectations, and assessment sensitivity. A fuel cell start-up scenario might activate expectations about reactant purge, membrane hydration, and gradual load application — expectations that do not apply during steady-state operation. Scenario reasoning would allow profiles to scope expectations to operational phases rather than treating all conditions uniformly.

### Richer reasoning

Expectation evaluation as input to hypothesis refinement, planning, and timeline analysis. When evidence is unexpected, candidate operational states drawn from profile knowledge could be ranked or filtered by which expectations they violate. Planning could consider not only what was observed but whether the gap between observed and expected behavior warrants investigation, derating, or shutdown. Timeline reasoning could track whether expectation violations are persistent, worsening, or resolving across reasoning cycles.

Each direction should be introduced only when it strengthens traceability and explainability without collapsing the separation between reasoning mechanics and domain knowledge.

---

## Guiding Principles

Expectation-based reasoning in ODIS rests on a concise set of principles:

- **Expectations are contextual.** The same measurement change can be expected in one operating mode and unexpected in another. Context determines which expectation applies.
- **Expectations are deterministic.** Given the same evidence and context, expectation evaluation produces the same result. Reasoning is reproducible and auditable.
- **Expectations are explainable.** Every judgment — expected, unexpected, or indeterminate — can be traced to an explicit engineering statement and the evidence that triggered evaluation.
- **Expectations enrich evidence.** Relationships describe what was observed. Expectations determine whether what was observed matters operationally.
- **Expectations belong to profiles.** Domain knowledge about how equipment should behave lives in operational profiles, not in the reasoning framework.

---

## Related documentation

- [Operational Reasoning Model](operational-reasoning-model.md) — the full reasoning pipeline, including the role of expected behavior
- [Fuel Cell Operational Knowledge](fuel-cell-operational-knowledge.md) — example domain knowledge that informs fuel cell expectations
- [Architecture](../architecture.md) — layer structure and the separation between framework reasoning and profile knowledge
- [Reasoning pipeline](../reasoning-pipeline.md) — stage-by-stage flow from observation to outcome
