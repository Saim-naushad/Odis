from dataclasses import dataclass

from application.contradiction_detector import (
    ContradictionDetector,
    OperationalContradiction,
)
from application.correlation_detector import (
    CorrelationDetector,
    MeasurementCorrelation,
)
from application.observation_group import ObservationGroup
from application.operational_profile import OperationalProfile


@dataclass(frozen=True)
class RelationshipAnalysis:
    correlations: tuple[MeasurementCorrelation, ...]
    contradictions: tuple[OperationalContradiction, ...]


class RelationshipAnalyzer:
    def __init__(
        self,
        *,
        profile: OperationalProfile | None = None,
        correlation_detector: CorrelationDetector | None = None,
        contradiction_detector: ContradictionDetector | None = None,
    ) -> None:
        resolved_profile = profile or OperationalProfile.default()

        self._correlation_detector = correlation_detector or CorrelationDetector(
            policy=resolved_profile.relationship_policy
        )
        self._contradiction_detector = contradiction_detector or ContradictionDetector(
            policy=resolved_profile.relationship_policy
        )

    def analyze(self, group: ObservationGroup) -> RelationshipAnalysis:
        correlations = self._correlation_detector.detect(group)
        contradictions = self._contradiction_detector.detect(group)
        return RelationshipAnalysis(
            correlations=correlations,
            contradictions=contradictions,
        )
