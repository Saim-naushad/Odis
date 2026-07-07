from __future__ import annotations

from dataclasses import dataclass

from application.relationship_policy import (
    DefaultRelationshipPolicy,
    RelationshipPolicy,
)


@dataclass(frozen=True)
class OperationalProfile:
    relationship_policy: RelationshipPolicy

    @classmethod
    def default(cls) -> OperationalProfile:
        return cls(relationship_policy=DefaultRelationshipPolicy())


def default_operational_profile() -> OperationalProfile:
    return OperationalProfile.default()

