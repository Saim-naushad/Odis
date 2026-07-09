"""Domain events emitted by application services.

These events contain only domain-relevant information and are intended to be
handled in-process by application-level handlers (e.g. monitoring publication).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class ObservationCreated:
    asset_id: str
    observation_id: str
    timestamp: datetime


@dataclass(frozen=True, slots=True)
class ReasoningCompleted:
    asset_id: str
    run_id: str
    timestamp: datetime


@dataclass(frozen=True, slots=True)
class ReasoningStarted:
    asset_id: str
    run_id: str
    timestamp: datetime


@dataclass(frozen=True, slots=True)
class RecommendationUpdated:
    asset_id: str
    run_id: str
    previous_recommendation: str | None
    new_recommendation: str
    timestamp: datetime

