from dataclasses import dataclass

from application.operational_state import OperationalState


@dataclass(frozen=True)
class Hypothesis:
    operational_state: OperationalState
    rationale: str
