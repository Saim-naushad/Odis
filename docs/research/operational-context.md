# Operational Context

## Purpose

Operational context is the information required to interpret observations correctly. Without context, a measurement is only a number. With context, the same number becomes evidence of coherent subsystem response, emerging fault, or benign transient.

**The same observations can have different meanings in different contexts.** A rising stack temperature is expected during load increase and unexpected during steady generation. A falling cell voltage is expected under rising discharge current and unexpected under stable load. The observation is identical; the operational meaning is not.

**Context precedes expectation evaluation.** Before the reasoning engine can ask whether behavior is expected, it must know what the system is doing. Expectations are defined relative to operating mode, load trajectory, environmental conditions, and other contextual factors. Evaluating an expectation without context is equivalent to applying a threshold: the judgment loses the information operators use to determine significance.

Operational context describes **what the system is doing**, allowing the reasoning engine to judge whether observed behavior is expected. It is not a diagnosis, not an assessment, and not a plan. It is the situational frame that makes expectation-based reasoning possible.

This document defines the concept of operational context within ODIS and explains why expectation-based reasoning depends on it. It is conceptual foundation for future `OperationalContext` implementation. It does not describe implementation details, introduce APIs, or modify existing architecture. For expectation evaluation, see [Expectation-Based Reasoning](expectation-based-reasoning.md). For the broader reasoning pipeline, see [Operational Reasoning Model](operational-reasoning-model.md).

---

## 1. Why Context Matters

Observations alone are insufficient for operational reasoning.

Industrial systems produce continuous streams of measurements — temperature, pressure, voltage, flow, and dozens of other quantities. Each reading answers a narrow question: *what was the value at this moment?* That question is necessary but does not answer the question operators actually ask: *does this value make sense right now?*

Consider three common observation patterns:

**Rising temperature**

Under increasing electrical load, rising temperature is the expected thermal response to higher waste heat generation. Under constant load, the same trend suggests cooling ineffectiveness, flow restriction, or a developing thermal fault. The measurement trend is identical; the operational meaning depends entirely on what the system was doing when the temperature rose.

**Falling voltage**

Under increasing current draw, a modest voltage decline is consistent with polarization behavior in electrochemical systems. Under stable current, a sustained voltage decline suggests performance loss, reactant limitation, or cell imbalance. The voltage change is the same observation; context determines whether it warrants investigation.

**Increasing pressure**

During a controlled load ramp, rising manifold pressure may reflect coordinated reactant delivery scaling with demand. During steady operation, rising pressure with stable flow may indicate restriction, valve malfunction, or blockage downstream. Pressure alone does not distinguish these cases.

In each example, the observation describes *what happened*. Context describes *what was happening when it happened*. Without context, the reasoning engine cannot distinguish expected subsystem response from unexpected divergence. Threshold monitoring treats all cases identically. Expectation-based reasoning does not — and cannot — without operational context.

**Operational reasoning requires context before interpretation.** Evidence detection can report that temperature is rising while load is stable. Expectation evaluation can judge whether that pattern is concerning. But the judgment requires knowing that load was stable — that the system was in a steady-generation context rather than a load-following context. Context is the prerequisite that transforms descriptive evidence into operationally meaningful evidence.

---

## 2. What Makes Up Operational Context?

Operational context is not a single variable. It is a composite description of the conditions under which observations are interpreted. The components below are **conceptual contributors** — categories of situational knowledge that inform expectation selection. They are not current implementation artifacts.

### Operating mode

The named phase of system operation: steady-state generation, load increase, load decrease, start-up, shutdown, emergency, or domain-specific modes such as charge, discharge, or standby. Operating mode determines which behavioral patterns are coherent. A fuel cell in start-up is governed by different expectations than one in steady generation. A battery in fast discharge is governed by different expectations than one in float charge.

### Recent trends

The directional behavior of key variables over a recent window: is load rising, falling, or stable? Are temperatures trending upward or settling? Recent trends supply trajectory information that a single snapshot cannot. A temperature of 75 °C is interpretable differently when load has been increasing for ten minutes than when load has been constant.

### Relationship evidence

Patterns already detected across measurements: correlations, contradictions, and other cross-measurement facts produced by relationship analysis. Relationship evidence is both an input to context formation and a product of observations viewed together. Rising temperature concurrent with rising current is relationship evidence that supports a load-following context.

### Timeline behavior

How operational conditions have evolved across prior reasoning cycles. A single unexpected pattern may be a transient. A pattern that persists or worsens across multiple cycles suggests a developing fault rather than momentary disturbance. Timeline behavior extends context beyond the current snapshot to include recent operational history.

### Operational objectives

What the system is trying to achieve at this moment: maximize output, maintain reserve capacity, protect equipment, complete a controlled shutdown, or balance efficiency against lifetime. Objectives influence which deviations matter. A efficiency loss during peak demand may be acceptable; the same loss during a protection-critical phase may not be.

### Environmental conditions

External factors that shape expected behavior: ambient temperature, humidity, altitude, grid conditions, cooling water supply temperature, and other environmental inputs. A stack temperature that is normal at 35 °C ambient may be abnormal at 20 °C ambient under the same load. Environmental conditions are part of context, not observations of the asset itself.

These components combine to answer a single question: **what is the system doing, and under what conditions?** The combination is domain-informed. A fuel cell context emphasizes load trajectory and reactant delivery state. A data center context emphasizes rack thermal distribution and redundancy posture. The reasoning model is shared; the contextual knowledge is profile-specific.

---

## 3. Context vs Observations

Observations and context answer different questions. Confusing them collapses the reasoning pipeline: if context is embedded in observations, interpretation becomes implicit and untraceable.

**Observations answer: *What happened?***

An observation is an immutable fact — a measurement recorded at a point in time. Stack temperature was 78 °C. Stack current was 42 A. Coolant outlet temperature was 65 °C. These are records of what was measured, on which asset, when, and in what units. Observations carry no interpretation, no threshold, and no judgment about significance.

**Context answers: *What was happening when it happened?***

Context describes the operational situation surrounding the observations. The system was operating at steady electrical load. Ambient temperature was 22 °C. The installation had been in continuous generation for four hours. Load had been stable for the preceding fifteen minutes. These are not sensor readings of the asset; they are situational facts that frame how observations should be interpreted.

### Practical engineering examples

**Example A: Coolant temperature rise**

| Layer | Content |
|---|---|
| Observation | Coolant outlet temperature increased from 58 °C to 64 °C over ten minutes. |
| Context | Electrical load was constant at 40 kW. Ambient temperature was stable at 18 °C. The system was in steady-state generation. |
| Interpretation | Rising coolant temperature without corresponding load increase is unexpected in this context. |

The observation records the temperature change. Context records that load and ambient conditions did not explain it. Interpretation — whether the pattern is expected — belongs to a later stage and depends on both.

**Example B: Voltage decline during load ramp**

| Layer | Content |
|---|---|
| Observation | Stack voltage decreased from 48 V to 45 V while current increased from 30 A to 55 A. |
| Context | The system was executing a controlled load increase. Fuel flow and air flow were tracking current demand. |
| Interpretation | Modest voltage decline during load increase is expected in this context. |

The observations record the electrical change. Context records that the change occurred during a coordinated load ramp with adequate reactant delivery. The same voltage decline without a load increase would carry different meaning under different context.

**Example C: Pressure spike during start-up**

| Layer | Content |
|---|---|
| Observation | Manifold pressure rose sharply over thirty seconds. |
| Context | The system was in start-up sequence, transitioning from purge to nominal reactant flow. |
| Interpretation | Transient pressure behavior during start-up may be expected; the same spike during steady operation would not be. |

Context does not replace observations. It situates them. A reasoning system that conflates the two cannot explain why a judgment was made, because the situational frame is no longer separable from the measurement record.

---

## 4. Context vs Expectations

Operational context and expectations are closely related but serve distinct roles. Context describes the situation. Expectations describe how the system should behave in that situation. Confusing them leads to circular reasoning: if expectations define context and context selects expectations, the pipeline has no stable foundation.

The relationship follows a clear sequence:

```
Operational Context
        ↓
Expectation Selection
        ↓
Expectation Evaluation
```

### Operational context

Context establishes what the system is doing: operating mode, load trajectory, environmental conditions, timeline behavior, and other situational factors described in Section 2. Context is descriptive. It does not judge whether behavior is correct.

### Expectation selection

Given a defined context, the reasoning process identifies which expectations are relevant. A fuel cell in load-following operation activates expectations about coordinated thermal, electrical, and reactant response. The same installation in idle operation activates a different set. Expectation selection is the bridge between situational description and behavioral judgment.

### Expectation evaluation

Observed evidence — trends, correlations, contradictions — is compared against the selected expectations. The evaluation produces a deterministic judgment: expected, unexpected, or indeterminate when context or evidence is insufficient.

**Context does not determine whether expectations are satisfied.** That is the role of expectation evaluation, which compares observed evidence against the selected reference. A rising temperature during steady load does not violate context; it violates the expectation that applies in a steady-load context.

**Context determines which expectations are relevant.** Without knowing that load is stable, the reasoning engine cannot select the expectation that temperature should remain relatively stable. Without knowing that load is increasing, it cannot select the expectation that temperature should rise. Context is the selector; expectations are the reference; evidence is the subject of comparison.

This separation keeps the reasoning pipeline inspectable. An engineer reviewing a judgment can identify three distinct artifacts: the situational frame (context), the engineering rule applied (expectation), and the observed pattern (evidence). Each can be examined independently.

---

## 5. Context Across Domains

Operational context is universal in structure and domain-specific in content. Every equipment type requires contextual knowledge to interpret observations, but the contextual factors differ by domain. ODIS profiles supply domain-specific context knowledge; the reasoning model supplies the structure through which context informs expectation selection.

### Fuel cells

Context for a PEM fuel cell installation includes electrical load trajectory, reactant delivery state (fuel flow, air flow, pressure), thermal conditions (stack temperature, coolant differential, ambient temperature), operating phase (start-up, steady generation, shutdown), and water management posture. A rising stack temperature is expected when context indicates load increase with adequate cooling flow. The same temperature rise is unexpected when context indicates steady load and stable ambient conditions. See [Fuel Cell Operational Knowledge](fuel-cell-operational-knowledge.md) for domain-specific examples.

### Battery systems

Context for a battery installation includes charge or discharge mode, state-of-charge trajectory, current magnitude and direction, cell balance state, thermal conditions, and whether the system is in normal operation, equalization, or protection-limited operation. Terminal voltage decline is expected during increasing discharge current. The same decline under stable current and balanced cells is unexpected and may indicate cell degradation or internal fault.

### Gas turbines

Context for a gas turbine includes load level, fuel flow, rotational speed, ambient conditions, operating phase (start-up, synchronization, baseload, part-load, shutdown), and transient state (settling after load change vs. steady-state). Exhaust temperature rise is expected during load increase with coordinated fuel flow. Rising exhaust temperature at stable fuel flow and constant load is unexpected and may indicate compressor fouling, combustion anomaly, or sensor fault.

### Industrial cooling

Context for an industrial cooling system includes chiller operating mode, cooling demand, refrigerant state, condenser and evaporator conditions, ambient wet-bulb temperature, and whether the system is in lead, lag, or standby configuration. Rising refrigerant pressure is expected during increasing cooling demand. Rising pressure at stable demand may indicate restriction, non-condensable accumulation, or control malfunction.

### Data centers

Context for a data center cooling and power installation includes IT load level, rack thermal distribution, airflow configuration, redundancy state (N, N+1, fault-tolerant), ambient conditions, and whether the facility is in normal operation, maintenance, or emergency cooling mode. Elevated rack inlet temperature is expected during peak compute load in hot weather. The same temperature at low load in moderate ambient conditions is unexpected and may indicate airflow failure or cooling unit degradation.

Each domain requires different contextual knowledge. All domains share the same reasoning model: observations produce evidence, context selects expectations, expectations are evaluated against evidence, and the result informs assessment and subsequent reasoning stages. Adding a new domain does not require redefining context. It requires authoring a profile that documents what contextual factors matter for that equipment type.

---

## 6. Relationship to ODIS

ODIS separates operational reasoning from domain knowledge. The framework defines how reasoning proceeds; profiles define what is known about a domain. Operational context sits at the boundary between evidence and expectation evaluation — after patterns have been detected and before they are judged against domain-specific behavioral rules.

The following flow represents **architectural direction**, not current implementation. Individual stages map to existing framework types where implemented today; the explicit operational context stage describes a conceptual extension of the reasoning model as ODIS evolves.

```
Observation
    ↓
Evidence
    ↓
Operational Context
    ↓
Expectation Evaluation
    ↓
Assessment
```

### Observation

Immutable facts recorded from the environment. Observations are the entry point: what was measured, on which asset, when, and in what units. They carry no interpretation and no contextual framing.

### Evidence

Meaningful patterns and relationships that emerge when observations are viewed together. Relationship analysis produces trends, correlations, and contradictions across measurement types. Evidence describes what happened across signals; it does not yet describe the situational frame.

### Operational Context

The situational description that frames evidence interpretation. Context incorporates operating mode, recent trends, timeline behavior, environmental conditions, and other factors described in Section 2. In the current framework, contextual information is implicit — embedded in assessment logic, profile knowledge, and operator-facing text rather than represented as an explicit reasoning artifact. The architectural direction is to make context a distinct, inspectable stage.

### Expectation Evaluation

Comparison of observed evidence against expectations selected for the current context. The evaluation produces a deterministic judgment: expected, unexpected, or indeterminate. Expectation evaluation is described conceptually in [Expectation-Based Reasoning](expectation-based-reasoning.md). It depends on operational context for expectation selection.

### Assessment

A structured summary of the reasoning outcome — what the system believes about operational conditions at a point in time, informed by evidence and expectation evaluation. Assessment occurs after context and expectations have been applied. It does not substitute for either.

This ordering matters. Context before expectation evaluation ensures that judgments are traceable to situational facts. Expectation evaluation before assessment ensures that conclusions reflect behavioral coherence, not merely pattern detection. Assessment before planning ensures that decisions consume interpreted conclusions, not raw telemetry.

The current ODIS pipeline implements observation grouping, relationship analysis, and structured assessment. Explicit operational context and expectation evaluation stages are forward-looking extensions aligned with the long-term vision described in [Operational Reasoning Model](operational-reasoning-model.md). Introducing them should strengthen traceability without collapsing the separation between reasoning mechanics and domain knowledge.

---

## 7. Future Directions

The following ideas represent possible future directions for operational context in ODIS. They are **conceptual only** — design explorations that may inform implementation when the reasoning model matures. None are current capabilities, commitments, or architectural changes.

### OperationalContext object

A first-class reasoning artifact that captures the situational frame at a point in time: operating mode, trend summary, environmental inputs, timeline posture, and references to the evidence that informed context formation. An explicit `OperationalContext` would make context inspectable, replayable, and separable from observations, evidence, and assessments. Profiles would supply the knowledge that populates context; the framework would supply the structure that carries it through the pipeline.

### Scenario reasoning

Profile-scoped definitions of operating scenarios — start-up, steady-state, shutdown, emergency — each bundling the contextual factors and active expectations for a named phase of operation. Scenario reasoning would allow context to be declared rather than inferred, reducing ambiguity when operating mode transitions are well-defined in domain practice.

### Context providers

Components or profile hooks that derive contextual facts from available evidence, timeline history, and external inputs. A context provider for a fuel cell might infer load-following operation from current trajectory and fuel flow coordination. A context provider for a data center might infer redundancy state from unit status signals. Context providers would keep context formation deterministic and profile-configurable without embedding domain assumptions into the framework.

### Context-aware planning

Planning that consumes not only structured assessment but the operational context that framed the assessment. A plan generated during start-up might recommend different actions than the same assessment pattern during steady operation. Context-aware planning would extend the existing `PlanningContext` concept to include situational framing, not only assessment-derived facts.

### Timeline-derived context

Context enriched by analysis across multiple reasoning cycles. A single cycle may show unexpected temperature behavior; timeline analysis may reveal whether the pattern is new, persistent, or worsening. Timeline-derived context would connect per-cycle situational framing to longitudinal operational history, complementing the `MonitoringTimeline` capabilities described in existing architecture documentation.

Each direction should be introduced only when it strengthens traceability and explainability without collapsing the separation between reasoning mechanics and domain knowledge.

---

## Guiding Principles

Operational context in ODIS rests on a concise set of principles:

- **Context precedes interpretation.** Observations gain operational meaning only when situated in a defined operational frame. Context must be established before evidence is judged.
- **Context selects expectations.** Context does not determine whether behavior is correct. It determines which expectations are relevant for evaluation.
- **Context is deterministic.** Given the same observations, timeline history, and profile knowledge, context formation produces the same situational description. Reasoning is reproducible and auditable.
- **Context is domain-informed.** What constitutes relevant context differs by equipment type. Profiles supply contextual knowledge; the framework supplies the reasoning structure.
- **Context enriches evidence.** Evidence describes observed relationships. Context describes the conditions under which those relationships should be interpreted. Together they enable expectation-based reasoning.

---

## Related documentation

- [Operational Reasoning Model](operational-reasoning-model.md) — the full reasoning pipeline, including the role of expected behavior
- [Expectation-Based Reasoning](expectation-based-reasoning.md) — how expectations depend on context for selection and evaluation
- [Fuel Cell Operational Knowledge](fuel-cell-operational-knowledge.md) — example domain knowledge that informs fuel cell operational context
- [Architecture](../architecture.md) — layer structure and the separation between framework reasoning and profile knowledge
- [Reasoning pipeline](../reasoning-pipeline.md) — stage-by-stage flow from observation to outcome
