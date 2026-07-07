# Architecture diagrams

These diagrams document the **current** ODIS implementation (not proposed future architecture). They are intentionally high-signal and GitHub-readable.

## Diagram 1 — High-Level Architecture

```mermaid
flowchart TB
    external["External Systems"]

    subgraph sources["Observation Sources"]
        csv["CsvObservationSource"]
        static["StaticObservationSource"]
        other["(Other adapters)\nimplement ObservationSource"]
        protocol["ObservationSource (Protocol)"]
        csv --> protocol
        static --> protocol
        other --> protocol
    end

    pipeline["ObservationPipeline"]
    session["ReasoningSession"]

    subgraph engine["Reasoning Engine (application components)"]
        trend["TrendDetector"]
        variation["VariationDetector"]
        assessor["OperationalSituationAssessor"]
        ctx["create_decision_context"]
        planner["DecisionPlanner"]
        action["record_action"]
        outcome["record_outcome"]
    end

    subgraph persistence["Persistence / Replay"]
        repos["Repositories\n(ReasoningRunRepository, ObservationRepository, ...)\n+ index/registry repositories"]
        replayer["ReasoningReplayer"]
        history["ReasoningHistory"]
    end

    subgraph analytics["Operational Analytics"]
        comparator["ReasoningComparator"]
        escalation["EscalationAnalyzer"]
        recurrence["RecurrenceAnalyzer"]
        stability["StabilityAnalyzer"]
    end

    subgraph operator["Operator Services"]
        summary["OperationalSummaryService"]
        queue["AttentionQueue"]
    end

    external --> sources
    protocol --> pipeline --> session --> engine

    session --> repos
    repos --> replayer --> history

    history --> comparator
    comparator --> escalation
    comparator --> recurrence
    comparator --> stability

    escalation --> summary
    recurrence --> summary
    stability --> summary
    summary --> queue
```

## Diagram 2 — Reasoning Pipeline

```mermaid
flowchart TB
    obs["Observation"]

    trendDetector["TrendDetector"]
    variationDetector["VariationDetector"]

    trend["DetectedTrend"]
    variation["DetectedVariation"]

    assessor["OperationalSituationAssessor\n(combines detector outputs)"]

    situation["OperationalSituationAssessor → OperationalSituation"]
    context["DecisionContext\n(create_decision_context)"]
    planner["DecisionPlanner"]
    plan["DecisionPlan"]
    action["Action\n(record_action)"]
    outcome["Outcome\n(record_outcome)"]

    obs --> trendDetector --> trend
    obs --> variationDetector --> variation

    trend --> assessor
    variation --> assessor
    assessor --> situation

    situation --> context --> planner --> plan --> action --> outcome
```

## Diagram 3 — Replay & Analytics

```mermaid
flowchart TB
    repos["Repositories\n(ReasoningRunRepository,\nReasoningRunIndexRepository,\nObservationRepository,\nSituationRepository,\nDecisionContextRepository,\nDecisionPlanRepository,\nReasoningRunRegistryRepository)"]

    replayer["ReasoningReplayer"]
    history["ReasoningHistory"]
    comparator["ReasoningComparator"]

    escalation["EscalationAnalyzer"]
    recurrence["RecurrenceAnalyzer"]
    stability["StabilityAnalyzer"]

    summary["OperationalSummaryService"]
    queue["AttentionQueue"]

    repos --> replayer --> history --> comparator

    comparator --> escalation
    comparator --> recurrence
    comparator --> stability

    escalation --> summary
    recurrence --> summary
    stability --> summary

    summary --> queue
```

## Diagram 4 — Integration Architecture

```mermaid
flowchart TB
    subgraph adapters["Adapters (infrastructure)"]
        csv["CsvObservationSource\n(CSV Source)"]
        static["StaticObservationSource\n(Static Source)"]
        future["Future Sources\n(file/SCADA/IoT/etc.)"]
    end

    protocol["ObservationSource (Protocol)"]
    pipeline["ObservationPipeline"]
    session["ReasoningSession"]

    csv --> protocol
    static --> protocol
    future --> protocol

    protocol --> pipeline --> session
```

