from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class OutcomeRecorded:
    outcome_id: str
    recorded_at: datetime
