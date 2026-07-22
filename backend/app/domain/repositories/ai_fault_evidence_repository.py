"""Repository contract for persisted AI fault-alert evidence."""

from __future__ import annotations

from typing import Protocol

from backend.app.domain.ai_fault_evidence import AiFaultEvidence


class AiFaultEvidenceRepository(Protocol):
    """Persist and query AI fault-alert evidence rows.

    `save` is this bridge's idempotency boundary (spec section 4): saving
    a row whose `id` (the source alert-transition event's own
    deterministic event_id) already exists must be rejected, exactly like
    `SqlAlchemyObservationRepository.save()` rejects a duplicate
    observation id.
    """

    def save(self, evidence: AiFaultEvidence) -> None:
        """Persist a new evidence row; raise if `evidence.id` already exists."""

    def get(self, evidence_id: str) -> AiFaultEvidence | None:
        """Return the evidence row for a source event id, if already processed."""

    def get_latest_for_asset(self, asset_id: str) -> AiFaultEvidence | None:
        """Return the most recently recorded evidence row for an asset, if any.

        This is the active-investigation lookup: a non-``CLEARED`` result
        is the asset's current open AI-fault investigation to update
        (class change) or clear; a ``CLEARED`` result (or no result at
        all) means the next confirmed alert starts a new occurrence.
        """

    def list_for_asset_grouped_by_investigation(
        self, asset_id: str, *, limit: int
    ) -> list[AiFaultEvidence]:
        """Return one row (the latest) per distinct investigation for an asset.

        ``limit`` bounds the number of *investigations* returned, not the
        number of underlying evidence rows scanned: an investigation with
        several lifecycle rows (e.g. a ``class_changed`` chain) must count
        once, not once per row, so an older investigation is never crowded
        out of a bounded history list by a newer investigation's own
        multiple transitions. Ordered most-recently-updated first.
        """

    def list_for_investigation(self, investigation_id: str) -> list[AiFaultEvidence]:
        """Return every evidence row for one investigation, oldest first.

        This is the full lifecycle: first confirmed alert through any
        class changes to the clearing transition, if any. Empty list if
        the investigation id is unknown.
        """
