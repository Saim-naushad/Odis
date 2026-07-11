from application.operational_profile import OperationalProfile
from application.reasoning.context import ReasoningContext
from application.reasoning.evidence_generation_stage import (
    EvidenceGenerationStage,
    generate_evidence_from_signals,
)
from application.reasoning.signal_extraction_stage import SignalExtractionStage
from domain.reasoning.evidence import EvidenceRole, EvidenceSourceSignal
from tests.builders import build_goal, build_observation_sequence


def test_evidence_generation_stage_requires_signals() -> None:
    context = ReasoningContext(
        goal=build_goal(),
        observations=build_observation_sequence([1.0, 2.0, 3.0]),
        profile=OperationalProfile.default(),
    )

    try:
        EvidenceGenerationStage().run(context)
        raise AssertionError("expected ValueError")
    except ValueError as exc:
        assert "signals must be extracted" in str(exc)


def test_evidence_generation_produces_canonical_structured_evidence() -> None:
    context = ReasoningContext(
        goal=build_goal(),
        observations=build_observation_sequence([10.0, 12.0, 14.0]),
        profile=OperationalProfile.default(),
    )
    context = SignalExtractionStage().run(context)
    context = EvidenceGenerationStage().run(context)

    evidence = context.artifacts.evidence
    evidence_ids = [item.id for item in evidence]

    assert EvidenceSourceSignal.LATEST_READING in evidence_ids
    assert EvidenceSourceSignal.DETECTED_TREND in evidence_ids
    assert EvidenceSourceSignal.DETECTED_VARIATION in evidence_ids
    assert EvidenceSourceSignal.RECENT_DELTA in evidence_ids
    assert EvidenceSourceSignal.SAMPLE_SUPPORT in evidence_ids
    assert all(item.source_signal for item in evidence)
    assert all(0.0 <= item.weight <= 1.0 for item in evidence)


def test_evidence_items_reference_typed_source_signals() -> None:
    context = ReasoningContext(
        goal=build_goal(),
        observations=build_observation_sequence([10.0, 12.0]),
        profile=OperationalProfile.default(),
    )
    context = SignalExtractionStage().run(context)
    assert context.artifacts.signals is not None

    evidence = generate_evidence_from_signals(signals=context.artifacts.signals)
    trend_evidence = next(
        item
        for item in evidence
        if item.source_signal == EvidenceSourceSignal.DETECTED_TREND
    )

    assert trend_evidence.role == EvidenceRole.PRIMARY_SUPPORT
    assert "Direction:" in trend_evidence.observed_value
