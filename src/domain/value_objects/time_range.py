from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class TimeRange:
    start: datetime
    end: datetime

    def __post_init__(self) -> None:
        if self.start > self.end:
            raise ValueError("start must not be after end")
