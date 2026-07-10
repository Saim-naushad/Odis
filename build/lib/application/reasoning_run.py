from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class ReasoningRun:
    id: str
    started_at: datetime
