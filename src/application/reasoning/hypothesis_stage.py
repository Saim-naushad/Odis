from __future__ import annotations

from dataclasses import dataclass

from application.reasoning.context import ReasoningContext, ReasoningSignals
from domain.entities.observation import Observation
from domain.reasoning.evidence import Evidence, EvidenceSourceSignal
from domain.reasoning.hypothesis import Hypothesis, HypothesisKind
from domain.value_objects.measurement_type import MeasurementType
from domain.value_objects.trend_direction import TrendDirection
from domain.value_objects.variation_level import VariationLevel


def _measurement_name(measurement_type: MeasurementType) -> str:
    return measurement_type.name


def _supports_cooling_degradation(signals: ReasoningSignals) -> bool:
    primary = signals.primary_observations
    if not primary:
        return False
    if _measurement_name(primary[0].measurement_type) != "stack_temperature":
        return False
    if signals.trend.direction != TrendDirection.INCREASING:
        return False
    if signals.variation.level != VariationLevel.LOW:
        return False
    stack_temperature = MeasurementType(name="stack_temperature")
    fuel_flow = MeasurementType(name="fuel_flow")
    return any(
        {correlation.measurement_a, correlation.measurement_b}
        == {stack_temperature, fuel_flow}
        for correlation in signals.relationship_analysis.correlations
    )


def _fuel_flow_decreasing(observations: tuple[Observation, ...]) -> bool:
    from application.trend_detector import TrendDetector

    fuel_flow = MeasurementType(name="fuel_flow")
    fuel_observations = [
        observation
        for observation in observations
        if observation.measurement_type == fuel_flow
    ]
    if len(fuel_observations) < 2:
        return False
    return (
        TrendDetector().detect(fuel_observations).direction == TrendDirection.DECREASING
    )


def _supports_hydrogen_supply(
    signals: ReasoningSignals,
    observations: tuple[Observation, ...],
) -> bool:
    if _fuel_flow_decreasing(observations):
        return True
    return signals.expectation_analysis.has_unexpected


def _supporting_ids_for_kind(
    *,
    kind: HypothesisKind,
    evidence: tuple[Evidence, ...],
) -> tuple[str, ...]:
    if kind == HypothesisKind.SENSOR_DRIFT:
        return tuple(
            item.id
            for item in evidence
            if item.source_signal
            in {
                EvidenceSourceSignal.RELATIONSHIP_CONTRADICTION,
                EvidenceSourceSignal.DETECTED_VARIATION,
            }
        )
    if kind in {HypothesisKind.COOLING_DEGRADATION, HypothesisKind.HYDROGEN_SUPPLY}:
        return tuple(
            item.id
            for item in evidence
            if item.source_signal == EvidenceSourceSignal.RELATIONSHIP_CORRELATION
        )
    return tuple(item.id for item in evidence[:2])


def generate_hypotheses_from_signals(
    *,
    signals: ReasoningSignals,
    evidence: tuple[Evidence, ...],
    observations: tuple[Observation, ...] = (),
) -> tuple[Hypothesis, ...]:
    """Generate a small deterministic hypothesis set from extracted signals."""
    primary = signals.primary_observations
    measurement_label = (
        _measurement_name(primary[0].measurement_type) if primary else "signal"
    )
    variation_high = signals.variation.level == VariationLevel.HIGH
    contradictions = bool(signals.relationship_analysis.contradictions)

    hypotheses: list[Hypothesis] = []

    if _supports_cooling_degradation(signals):
        hypotheses.append(
            Hypothesis(
                id="hypothesis-cooling-degradation",
                kind=HypothesisKind.COOLING_DEGRADATION,
                rationale=(
                    "Stack temperature is rising steadily with coupled fuel-flow "
                    "behavior, consistent with cooling degradation."
                ),
                supporting_evidence_ids=_supporting_ids_for_kind(
                    kind=HypothesisKind.COOLING_DEGRADATION,
                    evidence=evidence,
                ),
            )
        )
    elif _supports_hydrogen_supply(signals, observations):
        hypotheses.append(
            Hypothesis(
                id="hypothesis-hydrogen-supply",
                kind=HypothesisKind.HYDROGEN_SUPPLY,
                rationale=(
                    "Fuel delivery or coupled subsystem signals suggest a hydrogen "
                    "supply issue rather than isolated sensor noise."
                ),
                supporting_evidence_ids=_supporting_ids_for_kind(
                    kind=HypothesisKind.HYDROGEN_SUPPLY,
                    evidence=evidence,
                ),
            )
        )
    elif variation_high or contradictions:
        hypotheses.append(
            Hypothesis(
                id="hypothesis-sensor-drift",
                kind=HypothesisKind.SENSOR_DRIFT,
                rationale=(
                    "High variability or contradictory signals can indicate "
                    "measurement drift rather than a true change in "
                    f"{measurement_label}."
                ),
                supporting_evidence_ids=_supporting_ids_for_kind(
                    kind=HypothesisKind.SENSOR_DRIFT,
                    evidence=evidence,
                ),
            )
        )
    else:
        hypotheses.append(
            Hypothesis(
                id="hypothesis-load-change",
                kind=HypothesisKind.LOAD_CHANGE,
                rationale=(
                    "A short-lived load change can create transient shifts without a "
                    "persistent fault."
                ),
                supporting_evidence_ids=_supporting_ids_for_kind(
                    kind=HypothesisKind.LOAD_CHANGE,
                    evidence=evidence,
                ),
            )
        )

    if (
        signals.trend.direction == TrendDirection.INCREASING
        and len(primary) < 4
        and len(hypotheses) < 2
    ):
        hypotheses.append(
            Hypothesis(
                id="hypothesis-unknown",
                kind=HypothesisKind.UNKNOWN,
                rationale=(
                    "Limited observation history can reflect an unresolved operating "
                    "mode transition rather than a confirmed degradation pattern."
                ),
                supporting_evidence_ids=_supporting_ids_for_kind(
                    kind=HypothesisKind.UNKNOWN,
                    evidence=evidence,
                ),
            )
        )

    return tuple(hypotheses[:2])


@dataclass(frozen=True, slots=True)
class HypothesisStage:
    name: str = "Hypothesis Generation"

    def run(self, context: ReasoningContext) -> ReasoningContext:
        if context.artifacts.signals is None:
            raise ValueError("signals must be extracted before hypothesis generation")
        if not context.artifacts.evidence:
            raise ValueError("evidence must be generated before hypothesis generation")

        hypotheses = generate_hypotheses_from_signals(
            signals=context.artifacts.signals,
            evidence=context.artifacts.evidence,
            observations=context.observations,
        )
        return context.with_artifacts(hypotheses=hypotheses)
