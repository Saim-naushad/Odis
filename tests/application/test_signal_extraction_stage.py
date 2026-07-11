from application.profiles.fuel_cell_profile import FuelCellOperationalProfile
from application.reasoning.context import ReasoningContext
from application.reasoning.signal_extraction_stage import SignalExtractionStage
from domain.value_objects import TrendDirection, VariationLevel
from tests.builders import build_goal, build_observation_sequence


def test_signal_extraction_stage_matches_inline_detector_behavior() -> None:
    observations = build_observation_sequence([32.0, 36.5, 41.0, 45.5, 50.0])
    context = ReasoningContext(
        goal=build_goal(),
        observations=observations,
        profile=FuelCellOperationalProfile.default(),
    )

    result = SignalExtractionStage().run(context)
    signals = result.artifacts.signals

    assert signals is not None
    assert signals.trend.direction == TrendDirection.INCREASING
    assert signals.variation.level == VariationLevel.LOW
    assert len(signals.primary_observations) == len(observations)
    assert signals.operational_context.description == "Operational reasoning context"


def test_signal_extraction_stage_preserves_expectation_analysis() -> None:
    observations = build_observation_sequence([32.0, 36.5, 41.0])
    context = ReasoningContext(
        goal=build_goal(),
        observations=observations,
        profile=FuelCellOperationalProfile.default(),
    )

    result = SignalExtractionStage().run(context)
    signals = result.artifacts.signals

    assert signals is not None
    assert isinstance(signals.expectation_analysis.evaluations, tuple)
