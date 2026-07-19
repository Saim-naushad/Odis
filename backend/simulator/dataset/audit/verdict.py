"""Quality verdict (PR166 spec section 10).

Three possible verdicts, chosen from the worst finding severity present —
never forced positive. `blocking` findings mean the simulator or label
logic itself needs correction before any feature engineering; `high`
findings (with no `blocking`) mean the *dataset policy* (spec ranges,
split proportions, scenario plans) should change, but nothing about the
simulator or label semantics is wrong.
"""

from __future__ import annotations

from typing import Literal

from backend.simulator.dataset.audit.findings import Finding

Verdict = Literal[
    "READY FOR FEATURE ENGINEERING",
    "READY WITH DATASET POLICY CHANGES",
    "NOT READY — SIMULATOR OR LABEL CORRECTIONS REQUIRED",
]


def determine_verdict(findings: list[Finding]) -> Verdict:
    if any(f.severity == "blocking" for f in findings):
        return "NOT READY — SIMULATOR OR LABEL CORRECTIONS REQUIRED"
    if any(f.severity == "high" for f in findings):
        return "READY WITH DATASET POLICY CHANGES"
    return "READY FOR FEATURE ENGINEERING"
