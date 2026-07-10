from dataclasses import dataclass

from application.monitoring_timeline import MonitoringTimeline
from domain.value_objects.priority import Priority

_PRIORITY_RANK = {
    Priority.LOW: 0,
    Priority.MEDIUM: 1,
    Priority.HIGH: 2,
    Priority.CRITICAL: 3,
}


@dataclass(frozen=True)
class TimelineTrendAnalysis:
    priority_trend: str


class TimelineTrendAnalyzer:
    def analyze(
        self,
        timeline: MonitoringTimeline,
    ) -> TimelineTrendAnalysis:
        if timeline.count() < 2:
            return TimelineTrendAnalysis(priority_trend="stable")

        first_priority = timeline.runs[0].plan.priority
        last_priority = timeline.runs[-1].plan.priority

        first_rank = _PRIORITY_RANK[first_priority]
        last_rank = _PRIORITY_RANK[last_priority]

        if last_rank > first_rank:
            trend = "worsening"
        elif last_rank < first_rank:
            trend = "improving"
        else:
            trend = "stable"

        return TimelineTrendAnalysis(priority_trend=trend)
