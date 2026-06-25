from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class TimeRange:
    start: datetime
    end: datetime
