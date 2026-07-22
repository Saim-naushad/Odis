"""Entry point for the reasoning-bridge worker (PR178).

`python -m backend.app.reasoning_bridge_worker_main` — consumes confirmed
ML fault-alert events, deterministically corroborates them, and publishes
`fault_reasoning_result.v1`. See `docs/reasoning-bridge.md`.
"""

from __future__ import annotations

import signal
import sys

from prometheus_client import start_http_server

from backend.app.application.bootstrap import bootstrap_application_runtime
from backend.app.application.reasoning_bridge.reasoning_bridge_service import (
    ReasoningBridgeService,
)
from backend.app.application.reasoning_bridge.worker import ReasoningBridgeWorker
from backend.app.infrastructure.config.settings import get_settings
from backend.app.infrastructure.database.session import (
    create_db_engine,
    create_session_factory,
)
from backend.app.infrastructure.logging import configure_logging, get_logger
from backend.app.infrastructure.metrics import reasoning_bridge_metrics as metrics
from backend.app.infrastructure.persistence.sqlalchemy_unit_of_work import (
    SqlAlchemyUnitOfWork,
)
from backend.app.infrastructure.reasoning_bridge import kafka_io

logger = get_logger(__name__)

_shutdown_requested = False


def _handle_shutdown(signum: int, _frame: object) -> None:
    global _shutdown_requested
    _shutdown_requested = True
    logger.info("reasoning_bridge_worker_shutdown_requested", signal=signum)


def _should_stop() -> bool:
    return _shutdown_requested


def main() -> None:
    settings = get_settings()
    configure_logging(
        log_level=settings.log_level,
        environment=settings.environment,
    )

    if settings.database_url is None:
        logger.error("reasoning_bridge_worker_database_url_missing")
        sys.exit(1)
    if not settings.kafka_bootstrap_servers:
        logger.error("reasoning_bridge_worker_kafka_bootstrap_servers_missing")
        sys.exit(1)

    signal.signal(signal.SIGINT, _handle_shutdown)
    signal.signal(signal.SIGTERM, _handle_shutdown)

    start_http_server(settings.reasoning_bridge_metrics_port)
    metrics.record_worker_start()

    engine = create_db_engine(settings)
    session_factory = create_session_factory(engine)

    def unit_of_work_factory() -> SqlAlchemyUnitOfWork:
        return SqlAlchemyUnitOfWork(session_factory)

    # Wires this worker into the same outbox -> DomainEventBus -> Redis
    # pub/sub pipeline the API's SSE stream already reads from (mirrors
    # `worker_main.py`). Without this, a processed fault alert is
    # persisted but produces no live dashboard update — only the next
    # poll/refetch would see it.
    application_runtime = bootstrap_application_runtime(
        settings, unit_of_work_factory=unit_of_work_factory
    )
    if application_runtime.outbox_dispatcher is None:
        logger.error("reasoning_bridge_worker_outbox_dispatcher_missing")
        engine.dispose()
        sys.exit(1)

    service = ReasoningBridgeService(
        unit_of_work_factory,
        corroboration_window_seconds=(
            settings.reasoning_bridge_corroboration_window_seconds
        ),
        corroboration_sample_limit=(
            settings.reasoning_bridge_corroboration_sample_limit
        ),
        event_bus=application_runtime.domain_event_bus,
        outbox_dispatcher=application_runtime.outbox_dispatcher,
    )

    try:
        consumer = kafka_io.create_consumer(
            bootstrap_servers=settings.kafka_bootstrap_servers,
            topic=settings.reasoning_bridge_input_topic,
            group_id=settings.reasoning_bridge_consumer_group_id,
        )
        consumer.topics()  # verifies broker connectivity before consuming
    except Exception:
        logger.error(
            "reasoning_bridge_worker_kafka_connect_failed",
            bootstrap_servers=settings.kafka_bootstrap_servers,
            exc_info=True,
        )
        engine.dispose()
        sys.exit(1)

    producer = kafka_io.create_producer(
        bootstrap_servers=settings.kafka_bootstrap_servers
    )
    worker = ReasoningBridgeWorker(
        consumer=consumer,
        producer=producer,
        service=service,
        settings=settings,
    )

    logger.info(
        "reasoning_bridge_worker_started",
        input_topic=settings.reasoning_bridge_input_topic,
        output_topic=settings.reasoning_bridge_output_topic,
        consumer_group_id=settings.reasoning_bridge_consumer_group_id,
        metrics_port=settings.reasoning_bridge_metrics_port,
    )
    try:
        worker.run(_should_stop)
    finally:
        producer.flush()
        producer.close()
        consumer.close()
        engine.dispose()
        logger.info("reasoning_bridge_worker_stopped")


if __name__ == "__main__":
    main()
