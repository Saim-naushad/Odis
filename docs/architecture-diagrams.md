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
        stages["7-stage pipeline — see Diagram 2\n(Signal Extraction → Evidence → Hypothesis →\nAssessment → Confidence → Explanation → Planning)"]
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

`ReasoningSession.run()` executes seven `ReasoningStage` objects in order (`src/application/reasoning/`), each reading and extending a shared `ReasoningContext`:

```mermaid
flowchart TB
    obs["Observation"]

    subgraph s1["1. Signal Extraction (SignalExtractionStage)"]
        trendDetector["TrendDetector"]
        variationDetector["VariationDetector"]
        relAnalyzer["RelationshipAnalyzer"]
        ctxBuilder["OperationalContextBuilder"]
        expectations["OperationalProfile.evaluate_expectations()"]
    end
    signals["ReasoningSignals\n(trend, variation, relationships,\noperational context, expectation analysis)"]

    subgraph s2["2. Evidence Generation (EvidenceGenerationStage)"]
        genEvidence["generate_evidence_from_signals"]
    end
    evidence["Evidence[]"]

    subgraph s3["3. Hypothesis Generation (HypothesisStage)"]
        genHyp["generate_hypotheses_from_signals"]
    end
    hypotheses["Hypothesis[]"]

    subgraph s4["4. Assessment (AssessmentStage)"]
        assessor["OperationalSituationAssessor"]
    end
    situation["OperationalSituation +\nStructuredAssessment"]

    subgraph s5["5. Confidence (ConfidenceStage)"]
        scorer["score_assessment_confidence"]
    end
    confidence["ConfidenceBreakdown"]

    subgraph s6["6. Explanation (ExplanationStage)"]
        explainer["build_explanation"]
    end
    explanation["Explanation"]

    subgraph s7["7. Planning (PlanningStage)"]
        ctx["create_decision_context"]
        planner["DecisionPlanner"]
    end
    plan["DecisionContext + DecisionPlan"]

    action["Action\n(record_action)"]
    outcome["Outcome\n(record_outcome)"]

    obs --> s1 --> signals --> s2 --> evidence --> s3 --> hypotheses
    signals --> s4
    hypotheses --> s4
    s4 --> situation --> s5 --> confidence --> s6 --> explanation
    situation --> s7 --> plan --> action --> outcome
```

`Action` and `Outcome` are recorded by `record_action`/`record_outcome` immediately after the stage loop, not as `ReasoningStage` objects. See [Reasoning Pipeline](reasoning-pipeline.md) for a stage-by-stage description of what each artifact represents and why it exists.

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

