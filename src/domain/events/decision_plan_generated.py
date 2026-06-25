from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class DecisionPlanGenerated:
    plan_id: str
    generated_at: datetime
