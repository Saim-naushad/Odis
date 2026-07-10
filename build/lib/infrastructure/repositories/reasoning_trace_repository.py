from application.reasoning_trace import ReasoningTrace
from application.reasoning_trace_repository import ReasoningTraceRepository


class InMemoryReasoningTraceRepository(ReasoningTraceRepository):
    def __init__(self) -> None:
        self._storage: dict[str, ReasoningTrace] = {}

    def get_by_run_id(self, run_id: str) -> ReasoningTrace | None:
        return self._storage.get(run_id)

    def save(self, run_id: str, trace: ReasoningTrace) -> None:
        if run_id in self._storage:
            raise ValueError(f"reasoning trace for run_id {run_id!r} already exists")
        self._storage[run_id] = trace
