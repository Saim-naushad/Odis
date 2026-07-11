from __future__ import annotations

from dataclasses import dataclass

from application.reasoning.context import ReasoningContext, ReasoningSignals
from domain.entities.observation import Observation
from domain.reasoning.evidence import Evidence, EvidenceRole, EvidenceSourceSignal
from domain.value_objects.measurement_type import MeasurementType


def _measurement_type_label(measurement_type: MeasurementType | None) -> str:
    if measurement_type is None:
        return "unknown"
    return measurement_type.name


def _format_observed_value(observation: Observation) -> str:
    return f"{observation.value} {observation.unit}".strip()


def generate_evidence_from_signals(
    *, signals: ReasoningSignals
) -> tuple[Evidence, ...]:
    """Build canonical evidence from extracted signals.

    Mirrors the deterministic evidence shape used by platform explainability,
    but references typed signal information instead of post-plan artifacts.
    """
    primary_observations = list(signals.primary_observations)
    measurement_type = _measurement_type_label(
        primary_observations[0].measurement_type if primary_observations else None
    )
    evidences: list[Evidence] = []

    if primary_observations:
        latest = primary_observations[-1]
        evidences.append(
            Evidence(
                id=EvidenceSourceSignal.LATEST_READING,
                description="Latest recorded reading is considered in the decision.",
                source_signal=EvidenceSourceSignal.LATEST_READING,
                measurement_type=measurement_type,
                observed_value=_format_observed_value(latest),
                role=EvidenceRole.PRIMARY_SUPPORT,
                weight=0.35,
            )
        )

    evidences.append(
        Evidence(
            id=EvidenceSourceSignal.DETECTED_TREND,
            description=(
                "Directional trend derived from the primary measurement sequence."
            ),
            source_signal=EvidenceSourceSignal.DETECTED_TREND,
            measurement_type=measurement_type,
            observed_value=f"Direction: {signals.trend.direction.value}",
            role=EvidenceRole.PRIMARY_SUPPORT,
            weight=0.25,
        )
    )

    evidences.append(
        Evidence(
            id=EvidenceSourceSignal.DETECTED_VARIATION,
            description="Variability of the primary measurement sequence.",
            source_signal=EvidenceSourceSignal.DETECTED_VARIATION,
            measurement_type=measurement_type,
            observed_value=f"Variation: {signals.variation.level.value}",
            role=EvidenceRole.CONTEXT,
            weight=0.15,
        )
    )

    if len(primary_observations) >= 2:
        previous = primary_observations[-2]
        latest = primary_observations[-1]
        delta = latest.value - previous.value
        evidences.append(
            Evidence(
                id=EvidenceSourceSignal.RECENT_DELTA,
                description=(
                    "Change between the two most recent readings supports the "
                    "assessment."
                ),
                source_signal=EvidenceSourceSignal.RECENT_DELTA,
                measurement_type=measurement_type,
                observed_value=f"Δ {delta:.2f} {latest.unit} (latest - previous)",
                role=EvidenceRole.PRIMARY_SUPPORT,
                weight=0.3,
            )
        )

    if primary_observations:
        count = len(primary_observations)
        evidences.append(
            Evidence(
                id=EvidenceSourceSignal.SAMPLE_SUPPORT,
                description=(
                    "Multiple observations reduce the chance of a one-off anomaly."
                ),
                source_signal=EvidenceSourceSignal.SAMPLE_SUPPORT,
                measurement_type=measurement_type,
                observed_value=f"{count} supporting observations",
                role=EvidenceRole.CORROBORATING,
                weight=0.2 if count >= 3 else 0.15,
            )
        )

    for correlation in signals.relationship_analysis.correlations:
        evidence_id = (
            f"{EvidenceSourceSignal.RELATIONSHIP_CORRELATION}:"
            f"{correlation.measurement_a.name}:"
            f"{correlation.measurement_b.name}"
        )
        evidences.append(
            Evidence(
                id=evidence_id,
                description="Cross-measurement correlation supports interpretation.",
                source_signal=EvidenceSourceSignal.RELATIONSHIP_CORRELATION,
                measurement_type=measurement_type,
                observed_value=correlation.relationship,
                role=EvidenceRole.CORROBORATING,
                weight=0.2,
            )
        )

    for index, contradiction in enumerate(
        signals.relationship_analysis.contradictions
    ):
        evidence_id = f"{EvidenceSourceSignal.RELATIONSHIP_CONTRADICTION}:{index}"
        evidences.append(
            Evidence(
                id=evidence_id,
                description="Cross-measurement contradiction weakens certainty.",
                source_signal=EvidenceSourceSignal.RELATIONSHIP_CONTRADICTION,
                measurement_type=measurement_type,
                observed_value=contradiction.description,
                role=EvidenceRole.CONTRADICTING,
                weight=0.2,
            )
        )

    return tuple(evidences)


@dataclass(frozen=True, slots=True)
class EvidenceGenerationStage:
    name: str = "Evidence Generation"

    def run(self, context: ReasoningContext) -> ReasoningContext:
        if context.artifacts.signals is None:
            raise ValueError("signals must be extracted before evidence generation")

        evidence = generate_evidence_from_signals(signals=context.artifacts.signals)
        return context.with_artifacts(evidence=evidence)
