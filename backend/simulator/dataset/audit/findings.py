"""The one finding type every audit check reports through.

A single, uniform `Finding` shape (rather than a bespoke result type per
check module) is what lets `report.py` render every section — structural,
label-integrity, physical-behavior, leakage, etc. — through one table
renderer and lets `run_audit` decide the process exit code by scanning one
flat list, instead of each check module inventing its own pass/fail
protocol.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Severity = Literal["blocking", "high", "medium", "low"]

_SEVERITY_ORDER: dict[Severity, int] = {
    "blocking": 0,
    "high": 1,
    "medium": 2,
    "low": 3,
}


@dataclass(frozen=True)
class Finding:
    """One audit observation.

    `severity` follows the report's four-level scale (section 10 of the
    PR166 spec), not the three-level blocking/concerning/acceptable scale
    used only for physical-signature classification (`physical.py` maps
    that scale onto this one). `evidence` holds small, JSON-serializable
    supporting values (counts, example IDs, computed statistics) — never
    raw row data, to keep the report readable.
    """

    severity: Severity
    category: str
    message: str
    evidence: dict[str, object] = field(default_factory=dict)


def sort_findings(findings: list[Finding]) -> list[Finding]:
    """Most-severe first, stable within a severity (insertion order preserved)."""
    return sorted(findings, key=lambda f: _SEVERITY_ORDER[f.severity])


def has_blocking(findings: list[Finding]) -> bool:
    return any(f.severity == "blocking" for f in findings)
