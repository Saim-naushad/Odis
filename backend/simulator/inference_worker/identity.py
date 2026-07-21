"""Deterministic event identity (PR177 spec section 6).

Every existing ID-minting site in this codebase (`backend/app/application/
*`) uses random `uuid4()` — see `docs/kafka-fault-inference-worker.md`'s
"Delivery and idempotency semantics" section for the audit that found
this. This module is a deliberate, documented departure from that
convention: this worker's delivery model is at-least-once (manual offset
commit, no Kafka transactions), so replayed input (duplicate consumption,
worker restart, offset replay) must map to the *same* published event
identity rather than minting a new one each time — otherwise every replay
would emit an uncontrolled duplicate diagnosis/alert event downstream.

`uuid5` over a fixed private namespace, seeded from the fields that
define "the same logical output" for each event type, gives exactly
that: the same `(topic, source_timestamp, asset_id, model_system_version,
...)` always yields the same `event_id`, so a downstream consumer (PR178)
can deduplicate on `event_id` alone.
"""

from __future__ import annotations

from uuid import NAMESPACE_URL, uuid5

_NAMESPACE = uuid5(NAMESPACE_URL, "https://odis.internal/fault-inference-worker")


def deterministic_event_id(*parts: str) -> str:
    """Derive a stable event_id from an ordered tuple of identity fields.

    Callers pass fields in a fixed, documented order per event type (see
    `events.py`); the same ordered input always yields the same id.
    """
    return str(uuid5(_NAMESPACE, "|".join(parts)))
