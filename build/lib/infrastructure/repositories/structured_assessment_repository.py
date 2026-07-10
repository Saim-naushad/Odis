from application.structured_assessment import StructuredAssessment
from application.structured_assessment_repository import StructuredAssessmentRepository


class InMemoryStructuredAssessmentRepository(StructuredAssessmentRepository):
    def __init__(self) -> None:
        self._storage: dict[str, StructuredAssessment] = {}

    def get_by_run_id(self, run_id: str) -> StructuredAssessment | None:
        return self._storage.get(run_id)

    def save(self, run_id: str, assessment: StructuredAssessment) -> None:
        if run_id in self._storage:
            raise ValueError(
                f"structured assessment for run_id {run_id!r} already exists"
            )
        self._storage[run_id] = assessment
