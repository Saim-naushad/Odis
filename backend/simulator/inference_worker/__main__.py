"""Entry point: `python -m backend.simulator.inference_worker` (PR177 spec
section 14).

Loads and verifies the promoted bundle once, verifies Kafka connectivity,
starts the Prometheus metrics server, then consumes until SIGINT/SIGTERM,
flushing the producer and closing the consumer on the way out. Exits
nonzero on any unrecoverable startup failure — this worker never falls
back to an unverified or partially loaded model.
"""

from __future__ import annotations

import signal
import sys

from prometheus_client import start_http_server

from backend.simulator.inference.loader import (
    PromotedArtifactMismatchError,
    PromotedArtifactNotFoundError,
    UnexpectedArtifactFileError,
    load_promoted_fault_system,
)
from backend.simulator.inference.session import FaultInferenceManager
from backend.simulator.inference_worker import kafka_io, metrics
from backend.simulator.inference_worker.assembly import SampleAssembler
from backend.simulator.inference_worker.config import InferenceWorkerSettings
from backend.simulator.inference_worker.logging_setup import (
    configure_logging,
    get_logger,
)
from backend.simulator.inference_worker.worker import FaultInferenceStreamingWorker

logger = get_logger(__name__)

_shutdown_requested = False


def _handle_shutdown(signum: int, _frame: object) -> None:
    global _shutdown_requested
    _shutdown_requested = True
    logger.info("fault_inference_worker_shutdown_requested", signal=signum)


def _should_stop() -> bool:
    return _shutdown_requested


def main() -> None:
    settings = InferenceWorkerSettings()
    configure_logging(log_level="INFO")

    if not settings.bundle_dir.is_dir():
        logger.error(
            "fault_inference_worker_bundle_missing",
            bundle_dir=str(settings.bundle_dir),
        )
        sys.exit(1)

    try:
        system = load_promoted_fault_system(settings.bundle_dir)
    except (
        PromotedArtifactNotFoundError,
        UnexpectedArtifactFileError,
        PromotedArtifactMismatchError,
    ):
        logger.error(
            "fault_inference_worker_bundle_invalid",
            bundle_dir=str(settings.bundle_dir),
            exc_info=True,
        )
        sys.exit(1)

    logger.info(
        "fault_inference_worker_bundle_verified",
        model_system_version=system.system_version,
        model_hash=system.model_hash,
        policy_hash=system.policy_hash,
        feature_schema_version=system.feature_schema_version,
    )

    signal.signal(signal.SIGINT, _handle_shutdown)
    signal.signal(signal.SIGTERM, _handle_shutdown)

    start_http_server(settings.metrics_port)
    metrics.record_worker_start()

    try:
        consumer = kafka_io.create_consumer(
            bootstrap_servers=settings.kafka_bootstrap_servers,
            topic=settings.input_topic,
            group_id=settings.consumer_group_id,
        )
        consumer.topics()  # verifies broker connectivity before consuming
    except Exception:
        logger.error(
            "fault_inference_worker_kafka_connect_failed",
            bootstrap_servers=settings.kafka_bootstrap_servers,
            exc_info=True,
        )
        sys.exit(1)

    producer = kafka_io.create_producer(
        bootstrap_servers=settings.kafka_bootstrap_servers
    )
    manager = FaultInferenceManager(system=system)
    assembler = SampleAssembler(
        timeout_seconds=settings.assembly_timeout_seconds,
        max_buffered_timestamps_per_asset=settings.max_buffered_timestamps_per_asset,
        max_tracked_assets=settings.max_tracked_assets,
    )
    worker = FaultInferenceStreamingWorker(
        consumer=consumer,
        producer=producer,
        manager=manager,
        assembler=assembler,
        settings=settings,
    )

    logger.info(
        "fault_inference_worker_started",
        input_topic=settings.input_topic,
        results_topic=settings.results_topic,
        alert_transitions_topic=settings.alert_transitions_topic,
        data_quality_topic=settings.data_quality_topic,
        consumer_group_id=settings.consumer_group_id,
        metrics_port=settings.metrics_port,
    )
    try:
        worker.run(_should_stop)
    finally:
        producer.flush()
        producer.close()
        consumer.close()
        logger.info("fault_inference_worker_stopped")


if __name__ == "__main__":
    main()
