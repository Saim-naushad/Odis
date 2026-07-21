"""Streaming worker orchestration (PR177 spec sections 5, 6, 11).

`FaultInferenceStreamingWorker` is the one place consume → validate →
assemble → infer → publish → commit is wired together. Processing is
strictly sequential and single-threaded (spec section 11: "the first
implementation may process sequentially if expected load is small" —
Plant Alpha has 4 assets at a 15s telemetry cadence, well within a single
consumer's throughput), and offsets are committed only after every
publish a message's outcome required has succeeded (spec section 6) —
see `kafka_io.py`'s module docstring for the full delivery-semantics
rationale.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from backend.simulator.inference.session import FaultInferenceManager
from backend.simulator.inference_worker import kafka_io, metrics
from backend.simulator.inference_worker.assembly import (
    REASON_CONFLICTING_DUPLICATE,
    REASON_LATE,
    AssemblyOutcome,
    AssemblyStatus,
    SampleAssembler,
)
from backend.simulator.inference_worker.config import InferenceWorkerSettings
from backend.simulator.inference_worker.events import (
    TelemetryEventValidationError,
    build_data_quality_event,
    build_result_event,
    build_transition_event,
    validate_telemetry_event,
)
from backend.simulator.inference_worker.logging_setup import get_logger

logger = get_logger(__name__)


class FaultInferenceStreamingWorker:
    def __init__(
        self,
        *,
        consumer: Any,
        producer: Any,
        manager: FaultInferenceManager,
        assembler: SampleAssembler,
        settings: InferenceWorkerSettings,
    ) -> None:
        self._consumer = consumer
        self._producer = producer
        self._manager = manager
        self._assembler = assembler
        self._settings = settings

    def run(self, should_stop: Callable[[], bool]) -> None:
        while not should_stop():
            self.poll_once()

    def poll_once(self) -> None:
        records = self._consumer.poll(timeout_ms=self._settings.poll_timeout_ms)
        for _topic_partition, messages in records.items():
            for message in messages:
                if not self._handle_message(message):
                    self._report_gauges()
                    return
                self._consumer.commit()
        self._sweep_timeouts()
        self._report_gauges()

    # --- message handling --------------------------------------------------

    def _handle_message(self, record: Any) -> bool:
        metrics.record_telemetry_event_consumed()
        try:
            raw = json.loads(record.value.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError, AttributeError) as exc:
            metrics.record_malformed_event("malformed")
            logger.warning("fault_inference_telemetry_malformed", error=str(exc))
            return self._publish_data_quality(
                asset_id=None,
                source_timestamp=None,
                reason="malformed",
                detail=f"invalid JSON payload: {exc}",
            )

        try:
            event = validate_telemetry_event(raw)
        except TelemetryEventValidationError as exc:
            metrics.record_malformed_event(exc.reason_code)
            logger.warning(
                "fault_inference_telemetry_rejected",
                reason=exc.reason_code,
                error=str(exc),
            )
            return self._publish_data_quality(
                asset_id=raw.get("asset_id") if isinstance(raw, dict) else None,
                source_timestamp=None,
                reason="malformed",
                detail=str(exc),
            )

        outcomes = self._assembler.ingest(event, now=time.monotonic())
        return all(self._handle_assembly_outcome(outcome) for outcome in outcomes)

    def _handle_assembly_outcome(self, outcome: AssemblyOutcome) -> bool:
        if outcome.status is AssemblyStatus.PENDING:
            return True

        if outcome.status is AssemblyStatus.REJECTED:
            if outcome.reason == REASON_CONFLICTING_DUPLICATE:
                metrics.record_conflicting_duplicate()
            elif outcome.reason == REASON_LATE:
                metrics.record_late_sample()
            else:
                metrics.record_incomplete_sample_expiration()
            logger.warning(
                "fault_inference_telemetry_rejected",
                asset_id=outcome.asset_id,
                reason=outcome.reason,
                detail=outcome.detail,
                source_timestamp=(
                    outcome.source_timestamp.isoformat()
                    if outcome.source_timestamp
                    else None
                ),
            )
            return self._publish_data_quality(
                asset_id=outcome.asset_id,
                source_timestamp=outcome.source_timestamp,
                reason=outcome.reason or "malformed",
                detail=outcome.detail,
            )

        assert outcome.status is AssemblyStatus.COMPLETE
        metrics.record_sample_assembled()
        assert outcome.sample is not None
        return self._run_inference(outcome.sample)

    def _run_inference(self, sample: Any) -> bool:
        start = time.monotonic()
        result = self._manager.ingest(sample)
        metrics.record_inference_latency(time.monotonic() - start)
        metrics.record_event_lag(
            (datetime.now(UTC) - sample.timestamp).total_seconds()
        )
        metrics.record_result(result.status.value, result.diagnosed_class)
        logger.info(
            "fault_inference_result_computed",
            asset_id=result.asset_id,
            status=result.status.value,
            diagnosed_class=result.diagnosed_class,
            alert_state=result.alert_state,
        )

        result_event = build_result_event(result)
        if not kafka_io.publish_with_retry(
            self._producer,
            topic=self._settings.results_topic,
            key=result_event.asset_id,
            value=result_event.to_json_dict(),
            max_retries=self._settings.publish_max_retries,
            backoff_seconds=self._settings.publish_retry_backoff_seconds,
        ):
            metrics.record_publish_failure("results")
            return False

        transition_event = build_transition_event(result)
        if transition_event is not None:
            metrics.record_alert_transition(
                transition_event.transition_type, transition_event.diagnosed_class
            )
            logger.info(
                "fault_inference_alert_transition",
                asset_id=transition_event.asset_id,
                transition_type=transition_event.transition_type,
                from_state=transition_event.from_state,
                to_state=transition_event.to_state,
                diagnosed_class=transition_event.diagnosed_class,
            )
            if not kafka_io.publish_with_retry(
                self._producer,
                topic=self._settings.alert_transitions_topic,
                key=transition_event.asset_id,
                value=transition_event.to_json_dict(),
                max_retries=self._settings.publish_max_retries,
                backoff_seconds=self._settings.publish_retry_backoff_seconds,
            ):
                metrics.record_publish_failure("alert_transitions")
                return False

        return True

    def _publish_data_quality(
        self,
        *,
        asset_id: str | None,
        source_timestamp: datetime | None,
        reason: str,
        detail: str,
    ) -> bool:
        event = build_data_quality_event(
            asset_id=asset_id,
            source_timestamp=source_timestamp,
            reason=reason,
            detail=detail,
        )
        ok = kafka_io.publish_with_retry(
            self._producer,
            topic=self._settings.data_quality_topic,
            key=asset_id or "unknown",
            value=event.to_json_dict(),
            max_retries=self._settings.publish_max_retries,
            backoff_seconds=self._settings.publish_retry_backoff_seconds,
        )
        if not ok:
            metrics.record_publish_failure("data_quality")
        return ok

    def _sweep_timeouts(self) -> None:
        outcomes = self._assembler.sweep_timeouts(now=time.monotonic())
        for outcome in outcomes:
            # Best-effort: not tied to a consumer offset, so a publish
            # failure here is a monitoring gap, not a telemetry-loss gap
            # (the underlying messages' offsets were already committed
            # when each measurement was ingested). See docs.
            self._handle_assembly_outcome(outcome)

    def _report_gauges(self) -> None:
        metrics.record_active_asset_sessions(self._assembler.tracked_asset_count)
        metrics.record_assembly_buffer_size(
            self._assembler.total_buffered_timestamp_count()
        )
