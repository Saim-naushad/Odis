from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class OperationalSituationCreated:
    situation_id: str
    created_at: datetime
