from __future__ import annotations

from dataclasses import dataclass

from application.reasoning_session import ReasoningResult


@dataclass(frozen=True)
class MonitoringTimeline:
    runs: tuple[ReasoningResult, ...] = ()

    def append(self, result: ReasoningResult) -> MonitoringTimeline:
        return MonitoringTimeline(runs=(*self.runs, result))

    def latest(self) -> ReasoningResult | None:
        if not self.runs:
            return None
        return self.runs[-1]

    def previous(self) -> ReasoningResult | None:
        if len(self.runs) < 2:
            return None
        return self.runs[-2]

    def count(self) -> int:
        return len(self.runs)
