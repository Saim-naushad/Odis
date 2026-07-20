"""Loads each cohort's already-computed PR166 audit `summary.json` for the
study's "Physical audit" report section (spec section 6). Read-only —
this module never re-runs or re-thresholds the audit.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class AuditFinding:
    category: str
    severity: str
    message: str
    direction_consistency: float | None

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "severity": self.severity,
            "message": self.message,
            "direction_consistency": self.direction_consistency,
        }


@dataclass(frozen=True)
class CohortAudit:
    verdict: str
    finding_counts: dict[str, int]
    findings_at_or_above_medium: list[AuditFinding]

    @property
    def mean_physical_direction_consistency(self) -> float | None:
        values = [
            f.direction_consistency
            for f in self.findings_at_or_above_medium
            if f.category == "physical" and f.direction_consistency is not None
        ]
        return sum(values) / len(values) if values else None

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict,
            "finding_counts": self.finding_counts,
            "findings_at_or_above_medium": [
                f.to_json_dict() for f in self.findings_at_or_above_medium
            ],
            "mean_physical_direction_consistency": (
                self.mean_physical_direction_consistency
            ),
        }


_AT_OR_ABOVE_MEDIUM = frozenset({"medium", "high", "blocking"})


def load_cohort_audit(audit_directory: Path) -> CohortAudit:
    summary_path = audit_directory / "summary.json"
    data = json.loads(summary_path.read_text())
    findings = [
        AuditFinding(
            category=f["category"],
            severity=f["severity"],
            message=f["message"],
            direction_consistency=(
                f.get("evidence", {}).get("effect", {}).get("direction_consistency")
            ),
        )
        for f in data["findings"]
        if f["severity"] in _AT_OR_ABOVE_MEDIUM
    ]
    return CohortAudit(
        verdict=data["verdict"],
        finding_counts=data["finding_counts"],
        findings_at_or_above_medium=findings,
    )
