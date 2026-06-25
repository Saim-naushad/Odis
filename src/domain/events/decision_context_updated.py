from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class DecisionContextUpdated:
    context_id: str
    updated_at: datetime
