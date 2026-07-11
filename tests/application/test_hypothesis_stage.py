from application.operational_profile import OperationalProfile
from application.reasoning.context import ReasoningContext
from application.reasoning.evidence_generation_stage import EvidenceGenerationStage
from application.reasoning.hypothesis_stage import HypothesisStage
from application.reasoning.signal_extraction_stage import SignalExtractionStage
from domain.reasoning.hypothesis import HypothesisKind, hypothesis_display_title
from tests.builders import build_goal, build_observation_sequence


def _context_with_stages(
    observations: tuple[object, ...],
    *,
    profile: OperationalProfile | None = None,
) -> ReasoningContext:
    resolved_profile = profile or OperationalProfile.default()
    context = ReasoningContext(
        goal=build_goal(),
        observations=observations,
        profile=resolved_profile,
    )
    context = SignalExtractionStage().run(context)
    context = EvidenceGenerationStage().run(context)
    return HypothesisStage().run(context)


def test_hypothesis_stage_requires_prior_stages() -> None:
    context = ReasoningContext(
        goal=build_goal(),
        observations=build_observation_sequence([1.0, 2.0]),
        profile=OperationalProfile.default(),
    )

    try:
        HypothesisStage().run(context)
        raise AssertionError("expected ValueError")
    except ValueError as exc:
        assert "signals must be extracted" in str(exc)


def test_hypothesis_stage_generates_load_change_by_default() -> None:
    context = _context_with_stages(build_observation_sequence([10.0, 12.0, 14.0]))

    assert len(context.artifacts.hypotheses) >= 1
    assert context.artifacts.hypotheses[0].kind == HypothesisKind.LOAD_CHANGE
    assert (
        context.artifacts.hypotheses[0].display_title
        == hypothesis_display_title(HypothesisKind.LOAD_CHANGE)
    )


def test_hypothesis_stage_generates_sensor_drift_for_high_variation() -> None:
    observations = build_observation_sequence([10.0, 30.0, 5.0, 40.0])
    context = _context_with_stages(observations)

    assert context.artifacts.hypotheses[0].kind == HypothesisKind.SENSOR_DRIFT


def test_hypothesis_stage_adds_unknown_for_short_increasing_history() -> None:
    context = _context_with_stages(build_observation_sequence([10.0, 20.0]))

    kinds = {item.kind for item in context.artifacts.hypotheses}
    assert HypothesisKind.LOAD_CHANGE in kinds or HypothesisKind.UNKNOWN in kinds


def test_hypothesis_kind_titles_are_generated_from_canonical_identifiers() -> None:
    assert hypothesis_display_title(HypothesisKind.SENSOR_DRIFT) == "Sensor drift"
    assert hypothesis_display_title(HypothesisKind.UNKNOWN) == "Unknown cause"
