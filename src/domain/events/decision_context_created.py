from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class DecisionContextCreated:
    context_id: str
    created_at: datetime
