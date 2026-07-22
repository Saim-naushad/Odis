"""Investigation lifecycle decisions (spec section 10).

An "AI fault investigation" here is a lightweight, asset-scoped concept
distinct from `backend.app.domain.investigation.InvestigationEvent`
(which tracks an *operator's* response to a `Recommendation`, not a
system-detected fault occurrence — see `docs/reasoning-bridge.md`'s
"Reasoning bridge architecture" section for the audit that established
this distinction). Its identity is `investigation_id`, stable across one
occurrence's lifecycle: minted once on the first confirmed alert for an
asset, reused across any `class_changed` transitions, and retired when
`cleared`. A new confirmed alert after a clear always mints a *new*
`investigation_id` — it never reopens the cleared occurrence (spec
section 10: "create a new investigation occurrence, not silently reopen
an unrelated historical case").

The lookup is asset-scoped, not (asset, fault_class)-scoped: at most one
AI fault investigation is open per asset at a time, and `class_changed`
updates which fault class that same open investigation currently
concerns (see `AiFaultEvidenceRepository.get_latest_for_asset`'s
docstring).
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from backend.app.domain.ai_fault_evidence import AiFaultEvidence, InvestigationStatus


@dataclass(frozen=True)
class InvestigationDecision:
    investigation_id: str
    investigation_status: InvestigationStatus
    previous_diagnosed_fault_class: str | None
    is_new_investigation: bool


def decide_investigation(
    *,
    transition_type: str,
    fault_class: str,
    active: AiFaultEvidence | None,
) -> InvestigationDecision:
    has_active_open = active is not None and active.investigation_status == "OPEN"

    if transition_type == "cleared":
        if has_active_open:
            assert active is not None
            return InvestigationDecision(
                investigation_id=active.investigation_id,
                investigation_status="CLEARED",
                previous_diagnosed_fault_class=active.diagnosed_fault_class,
                is_new_investigation=False,
            )
        # Defensive: a `cleared` transition with no active open investigation
        # on record (e.g. worker restart lost in-memory FSM history, or an
        # out-of-order replay) — still record it, immediately CLEARED, so the
        # event is traceable rather than silently dropped.
        return InvestigationDecision(
            investigation_id=str(uuid4()),
            investigation_status="CLEARED",
            previous_diagnosed_fault_class=None,
            is_new_investigation=True,
        )

    # confirmed or class_changed
    if has_active_open:
        assert active is not None
        previous = (
            active.diagnosed_fault_class
            if active.diagnosed_fault_class != fault_class
            else None
        )
        return InvestigationDecision(
            investigation_id=active.investigation_id,
            investigation_status="OPEN",
            previous_diagnosed_fault_class=previous,
            is_new_investigation=False,
        )

    return InvestigationDecision(
        investigation_id=str(uuid4()),
        investigation_status="OPEN",
        previous_diagnosed_fault_class=None,
        is_new_investigation=True,
    )
