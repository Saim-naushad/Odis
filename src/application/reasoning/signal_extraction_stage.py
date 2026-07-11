from __future__ import annotations

from dataclasses import dataclass

from application.observation_group import ObservationGroup
from application.operational_context_builder import OperationalContextBuilder
from application.reasoning.context import (
    ReasoningContext,
    ReasoningSignals,
    primary_measurement_observations,
)
from application.relationship_analysis import RelationshipAnalyzer
from application.trend_detector import TrendDetector
from application.variation_detector import VariationDetector


@dataclass(frozen=True, slots=True)
class SignalExtractionStage:
    """Wrap existing detector and analyzer calls without changing their behavior."""

    name: str = "Signal Extraction"

    def run(self, context: ReasoningContext) -> ReasoningContext:
        observations = context.observations

        if len(observations) < 2:
            TrendDetector().detect(observations)

        primary_observations = primary_measurement_observations(observations)
        trend = TrendDetector().detect(primary_observations)
        variation = VariationDetector().detect(primary_observations)
        observation_group = ObservationGroup(
            asset_id=observations[0].asset_id,
            observations=observations,
        )
        relationship_analysis = RelationshipAnalyzer(
            profile=context.profile,
        ).analyze(observation_group)
        operational_context = OperationalContextBuilder().build(
            description="Operational reasoning context",
        )
        expectation_analysis = context.profile.evaluate_expectations(
            operational_context,
            relationship_analysis,
        )

        signals = ReasoningSignals(
            trend=trend,
            variation=variation,
            relationship_analysis=relationship_analysis,
            operational_context=operational_context,
            expectation_analysis=expectation_analysis,
            primary_observations=primary_observations,
        )
        return context.with_artifacts(signals=signals)
