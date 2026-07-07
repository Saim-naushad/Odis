from __future__ import annotations

from dataclasses import dataclass

from application.relationship_policy import (
    DefaultRelationshipPolicy,
    RelationshipPolicy,
)


@dataclass(frozen=True)
class OperationalProfile:
    relationship_policy: RelationshipPolicy


def DefaultOperationalProfile() -> OperationalProfile:
    return OperationalProfile(relationship_policy=DefaultRelationshipPolicy())

