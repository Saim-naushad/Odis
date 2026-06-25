from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class ObservationRecorded:
    observation_id: str
    recorded_at: datetime
