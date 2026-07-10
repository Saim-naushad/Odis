from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from application.expectation_analysis import ExpectationAnalysis
from application.relationship_policy import (
    DefaultRelationshipPolicy,
    RelationshipPolicy,
)

if TYPE_CHECKING:
    from application.operational_context import OperationalContext
    from application.relationship_analysis import RelationshipAnalysis


@dataclass(frozen=True)
class OperationalProfile:
    relationship_policy: RelationshipPolicy

    @classmethod
    def default(cls) -> OperationalProfile:
        return cls(relationship_policy=DefaultRelationshipPolicy())

    def evaluate_expectations(
        self,
        operational_context: OperationalContext,
        relationship_analysis: RelationshipAnalysis,
    ) -> ExpectationAnalysis:
        _ = operational_context
        _ = relationship_analysis
        return ExpectationAnalysis(evaluations=())


def default_operational_profile() -> OperationalProfile:
    return OperationalProfile.default()

