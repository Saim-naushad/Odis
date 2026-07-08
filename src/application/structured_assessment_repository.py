from abc import ABC, abstractmethod

from application.structured_assessment import StructuredAssessment


class StructuredAssessmentRepository(ABC):
    @abstractmethod
    def get_by_run_id(self, run_id: str) -> StructuredAssessment | None:
        pass

    @abstractmethod
    def save(self, run_id: str, assessment: StructuredAssessment) -> None:
        pass
