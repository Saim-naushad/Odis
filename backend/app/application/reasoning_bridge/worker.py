"""Reasoning-bridge worker orchestration (spec section 15).

Consume → validate → deduplicate/process (`ReasoningBridgeService`,
which is itself the atomic persistence unit) → publish
`fault_reasoning_result.v1` → commit offset, in that order. The consumer
offset is committed only after the triggering message's required
persistence (inside `process_alert_transition`'s own UnitOfWork) *and*
publish have both succeeded — matching PR177's own worker delivery
semantics exactly (`backend.simulator.inference_worker.worker`).

Transaction boundary, spelled out: persistence and Kafka publication are
two separate operations (Kafka has no two-phase commit with PostgreSQL),
so this is not a distributed transaction — it is an idempotent
at-least-once pipeline. If persistence succeeds but the publish then
fails, the offset is not committed, the message is redelivered, and
`ReasoningBridgeService.process_alert_transition` becomes a no-op replay
(the evidence row already exists) that still re-attempts the publish
with the same deterministic `event_id` — so a downstream consumer sees
at most one logical event, never a duplicate.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from typing import Any

from backend.app.application.reasoning_bridge.input_events import (
    AlertTransitionValidationError,
    validate_alert_transition,
)
from backend.app.application.reasoning_bridge.output_events import (
    build_reasoning_result_event,
)
from backend.app.application.reasoning_bridge.reasoning_bridge_service import (
    ReasoningBridgeService,
    UnsupportedFaultClassError,
)
from backend.app.infrastructure.config.settings import Settings
from backend.app.infrastructure.logging import get_logger
from backend.app.infrastructure.metrics import reasoning_bridge_metrics as metrics
from backend.app.infrastructure.reasoning_bridge import kafka_io

logger = get_logger(__name__)


class ReasoningBridgeWorker:
    def __init__(
        self,
        *,
        consumer: Any,
        producer: Any,
        service: ReasoningBridgeService,
        settings: Settings,
    ) -> None:
        self._consumer = consumer
        self._producer = producer
        self._service = service
        self._settings = settings

    def run(self, should_stop: Callable[[], bool]) -> None:
        while not should_stop():
            self.poll_once()

    def poll_once(self) -> None:
        records = self._consumer.poll(
            timeout_ms=self._settings.reasoning_bridge_poll_timeout_ms
        )
        for _topic_partition, messages in records.items():
            for message in messages:
                if not self._handle_message(message):
                    return
                self._consumer.commit()

    def _handle_message(self, record: Any) -> bool:
        metrics.record_alert_transition_consumed()
        start = time.monotonic()

        try:
            raw = json.loads(record.value.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError, AttributeError) as exc:
            metrics.record_malformed_event("malformed")
            logger.warning("reasoning_bridge_alert_malformed", error=str(exc))
            return True

        try:
            validated = validate_alert_transition(raw)
        except AlertTransitionValidationError as exc:
            metrics.record_malformed_event(exc.reason_code)
            logger.warning(
                "reasoning_bridge_alert_rejected",
                reason=exc.reason_code,
                error=str(exc),
            )
            return True

        try:
            outcome = self._service.process_alert_transition(validated)
        except UnsupportedFaultClassError as exc:
            metrics.record_malformed_event("unsupported_fault_class")
            logger.warning(
                "reasoning_bridge_alert_rejected",
                reason="unsupported_fault_class",
                fault_class=exc.fault_class,
            )
            return True
        except Exception:
            metrics.record_failure()
            logger.error(
                "reasoning_bridge_processing_failed",
                source_event_id=validated.event_id,
                asset_id=validated.asset_id,
                exc_info=True,
            )
            return False

        metrics.record_processing_latency(time.monotonic() - start)

        if outcome.is_duplicate:
            metrics.record_duplicate_event_ignored()
            logger.info(
                "reasoning_bridge_duplicate_ignored",
                source_event_id=validated.event_id,
                asset_id=validated.asset_id,
            )
            return True

        self._record_lifecycle_metrics(validated, outcome)

        output_event = build_reasoning_result_event(outcome.evidence)
        published = kafka_io.publish_with_retry(
            self._producer,
            topic=self._settings.reasoning_bridge_output_topic,
            key=output_event.asset_id,
            value=output_event.to_json_dict(),
            max_retries=self._settings.reasoning_bridge_publish_max_retries,
            backoff_seconds=(
                self._settings.reasoning_bridge_publish_retry_backoff_seconds
            ),
        )
        if not published:
            metrics.record_publish_failure()
            logger.warning(
                "reasoning_bridge_publish_failed",
                source_event_id=validated.event_id,
                asset_id=validated.asset_id,
            )
            return False

        recommendation = outcome.evidence.recommendation
        logger.info(
            "reasoning_bridge_result_published",
            source_event_id=validated.event_id,
            asset_id=validated.asset_id,
            diagnosed_class=outcome.evidence.diagnosed_fault_class,
            corroboration_result=outcome.evidence.corroboration_result,
            investigation_id=outcome.evidence.investigation_id,
            recommendation_status=(
                recommendation.status if recommendation is not None else None
            ),
        )
        return True

    def _record_lifecycle_metrics(self, validated: Any, outcome: Any) -> None:
        evidence = outcome.evidence
        metrics.record_corroboration_result(evidence.corroboration_result)

        if validated.transition_type == "cleared":
            metrics.record_clear_transition_processed()
        elif validated.transition_type == "class_changed":
            metrics.record_class_change_update()
            metrics.record_investigation_updated()
        elif outcome.is_new_investigation:
            metrics.record_investigation_created()
        else:
            metrics.record_investigation_updated()

        recommendation = evidence.recommendation
        if recommendation is not None:
            if recommendation.status == "produced":
                metrics.record_recommendation_produced()
            else:
                metrics.record_recommendation_withheld()
