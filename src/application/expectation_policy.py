from __future__ import annotations

from dataclasses import dataclass

from application.expectation import Expectation
from application.operational_scenario import OperationalScenario


@dataclass(frozen=True)
class ExpectationPolicy:
    scenario: OperationalScenario
    expectations: tuple[Expectation, ...]
