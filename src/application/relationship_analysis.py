from dataclasses import dataclass

from application.contradiction_detector import (
    ContradictionDetector,
    OperationalContradiction,
)
from application.correlation_detector import CorrelationDetector, MeasurementCorrelation
from application.observation_group import ObservationGroup


@dataclass(frozen=True)
class RelationshipAnalysis:
    correlations: tuple[MeasurementCorrelation, ...]
    contradictions: tuple[OperationalContradiction, ...]


class RelationshipAnalyzer:
    def __init__(
        self,
        correlation_detector: CorrelationDetector | None = None,
        contradiction_detector: ContradictionDetector | None = None,
    ) -> None:
        self._correlation_detector = correlation_detector or CorrelationDetector()
        self._contradiction_detector = contradiction_detector or ContradictionDetector()

    def analyze(self, group: ObservationGroup) -> RelationshipAnalysis:
        correlations = self._correlation_detector.detect(group)
        contradictions = self._contradiction_detector.detect(group)
        return RelationshipAnalysis(
            correlations=correlations,
            contradictions=contradictions,
        )
