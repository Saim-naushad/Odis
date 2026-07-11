"""Bounded monitoring read-path specifications."""

from __future__ import annotations

import time
from collections.abc import Generator
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
from sqlalchemy.orm import Session

from application.reasoning_run import ReasoningRun
from application.reasoning_run_index import ReasoningRunIndex
from backend.app.application.digital_twin_service import DigitalTwinService
from backend.app.application.monitoring_service import (
    DEFAULT_MONITORING_HISTORY_LIMIT,
    MonitoringService,
)
from backend.app.infrastructure.cache.memory_digital_twin_cache import (
    MemoryDigitalTwinCache,
)
from backend.app.infrastructure.config.settings import Settings
from backend.app.infrastructure.database import models as _models  # noqa: F401
from backend.app.infrastructure.database.base import Base
from backend.app.infrastructure.database.session import (
    create_db_engine,
    create_session_factory,
)
from backend.app.infrastructure.repositories.decision_context_repository import (
    SqlAlchemyDecisionContextRepository,
)
from backend.app.infrastructure.repositories.decision_plan_repository import (
    SqlAlchemyDecisionPlanRepository,
)
from backend.app.infrastructure.repositories.observation_repository import (
    SqlAlchemyObservationRepository,
)
from backend.app.infrastructure.repositories.reasoning_run_index_repository import (
    SqlAlchemyReasoningRunIndexRepository,
)
from backend.app.infrastructure.repositories.reasoning_run_repository import (
    SqlAlchemyReasoningRunRepository,
)
from backend.app.infrastructure.repositories.reasoning_trace_repository import (
    SqlAlchemyReasoningTraceRepository,
)
from backend.app.infrastructure.repositories.situation_repository import (
    SqlAlchemySituationRepository,
)
from backend.app.infrastructure.repositories.structured_assessment_repository import (
    SqlAlchemyStructuredAssessmentRepository,
)
from backend.app.infrastructure.repositories.timeline_repository import (
    SqlAlchemyTimelineRepository,
)
from domain.entities.decision_context import DecisionContext
from domain.entities.decision_plan import DecisionPlan
from domain.entities.operational_situation import OperationalSituation
from domain.value_objects.priority import Priority
from tests.builders import DEFAULT_TIMESTAMP, build_observation


@pytest.fixture
def sqlite_settings() -> Settings:
    return Settings(database_url="sqlite://", forecast_enabled=False)


@pytest.fixture
def db_session(sqlite_settings: Settings) -> Generator[Session, None, None]:
    engine = create_db_engine(sqlite_settings)
    Base.metadata.create_all(engine)
    session_factory = create_session_factory(engine)
    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
        engine.dispose()


def _monitoring_service(db_session: Session) -> MonitoringService:
    return MonitoringService(
        observation_repository=SqlAlchemyObservationRepository(db_session),
        reasoning_run_repository=SqlAlchemyReasoningRunRepository(db_session),
        reasoning_run_index_repository=SqlAlchemyReasoningRunIndexRepository(
            db_session
        ),
        situation_repository=SqlAlchemySituationRepository(db_session),
        structured_assessment_repository=SqlAlchemyStructuredAssessmentRepository(
            db_session
        ),
        reasoning_trace_repository=SqlAlchemyReasoningTraceRepository(db_session),
        decision_context_repository=SqlAlchemyDecisionContextRepository(db_session),
        decision_plan_repository=SqlAlchemyDecisionPlanRepository(db_session),
        timeline_repository=SqlAlchemyTimelineRepository(db_session),
    )


def _seed_minimal_run(
    db_session: Session,
    *,
    run_id: str,
    asset_id: str,
    started_at: datetime,
    observation_id: str,
) -> None:
    observation = build_observation(
        id=observation_id,
        asset_id=asset_id,
        timestamp=started_at,
        value=42.0,
    )
    SqlAlchemyObservationRepository(db_session).save(observation)

    SqlAlchemyReasoningRunRepository(db_session).save(
        ReasoningRun(id=run_id, started_at=started_at)
    )

    situation = OperationalSituation(
        id=f"situation-{run_id}",
        goal_id="goal-1",
        observation_ids=(observation_id,),
        assessment="stable",
    )
    context = DecisionContext(
        id=f"context-{run_id}",
        goal_id="goal-1",
        situation_id=situation.id,
        assessment="stable",
        created_at=started_at,
    )
    plan = DecisionPlan(
        id=f"plan-{run_id}",
        context_id=context.id,
        created_at=started_at,
        priority=Priority.LOW,
        recommendation="Continue monitoring",
        justification="Operations remain within expected bounds.",
    )
    SqlAlchemySituationRepository(db_session).save(situation)
    SqlAlchemyDecisionContextRepository(db_session).save(context)
    SqlAlchemyDecisionPlanRepository(db_session).save(plan)

    SqlAlchemyReasoningRunIndexRepository(db_session).save(
        ReasoningRunIndex(
            run_id=run_id,
            observation_ids=(observation_id,),
            situation_id=situation.id,
            context_id=context.id,
            plan_id=plan.id,
            action_id=f"action-{run_id}",
            outcome_id=f"outcome-{run_id}",
            asset_id=asset_id,
        )
    )


def _seed_noise_runs(
    db_session: Session,
    *,
    asset_id: str,
    count: int,
    start_index: int = 0,
) -> None:
    for offset in range(count):
        index = start_index + offset
        _seed_minimal_run(
            db_session,
            run_id=f"noise-{asset_id}-{index}",
            asset_id=asset_id,
            started_at=DEFAULT_TIMESTAMP + timedelta(seconds=index),
            observation_id=f"obs-{asset_id}-{index}",
        )


def test_list_by_asset_returns_newest_first_with_limit(
    db_session: Session,
) -> None:
    target_asset = "asset-target"
    for offset in range(5):
        _seed_minimal_run(
            db_session,
            run_id=f"run-{offset}",
            asset_id=target_asset,
            started_at=DEFAULT_TIMESTAMP + timedelta(minutes=offset),
            observation_id=f"obs-target-{offset}",
        )

    repository = SqlAlchemyReasoningRunIndexRepository(db_session)
    newest_two = repository.list_by_asset(target_asset, limit=2, newest_first=True)

    assert [index.run_id for index in newest_two] == ["run-4", "run-3"]


def test_get_history_respects_default_limit_and_chronological_order(
    db_session: Session,
) -> None:
    target_asset = "asset-history"
    total_runs = DEFAULT_MONITORING_HISTORY_LIMIT + 25
    for offset in range(total_runs):
        _seed_minimal_run(
            db_session,
            run_id=f"hist-run-{offset}",
            asset_id=target_asset,
            started_at=DEFAULT_TIMESTAMP + timedelta(seconds=offset),
            observation_id=f"obs-hist-{offset}",
        )

    service = _monitoring_service(db_session)
    history = service.get_history_for_asset(target_asset)

    assert history is not None
    assert len(history) == DEFAULT_MONITORING_HISTORY_LIMIT
    run_ids = [item.run.id for item in history]
    expected_first = f"hist-run-{total_runs - DEFAULT_MONITORING_HISTORY_LIMIT}"
    expected_last = f"hist-run-{total_runs - 1}"
    assert run_ids[0] == expected_first
    assert run_ids[-1] == expected_last
    assert run_ids == sorted(run_ids, key=lambda run_id: int(run_id.rsplit("-", 1)[-1]))


def test_get_latest_does_not_enumerate_all_run_indexes(
    db_session: Session,
) -> None:
    target_asset = "asset-fast"
    _seed_noise_runs(db_session, asset_id="asset-noise-a", count=1500, start_index=0)
    _seed_noise_runs(db_session, asset_id="asset-noise-b", count=1500, start_index=1500)
    for offset in range(3):
        _seed_minimal_run(
            db_session,
            run_id=f"target-run-{offset}",
            asset_id=target_asset,
            started_at=DEFAULT_TIMESTAMP + timedelta(hours=offset),
            observation_id=f"obs-fast-{offset}",
        )

    service = _monitoring_service(db_session)
    index_repo = service._reasoning_run_index_repository

    with patch.object(
        index_repo,
        "list",
        side_effect=AssertionError("get_latest must not scan all run indexes"),
    ):
        latest = service.get_latest_for_asset(target_asset)

    assert latest is not None
    assert latest.run.id == "target-run-2"


def test_digital_twin_assembly_does_not_enumerate_all_run_indexes(
    db_session: Session,
) -> None:
    target_asset = "asset-twin"
    _seed_noise_runs(db_session, asset_id="asset-noise-c", count=2000, start_index=0)
    _seed_minimal_run(
        db_session,
        run_id="twin-run-latest",
        asset_id=target_asset,
        started_at=DEFAULT_TIMESTAMP + timedelta(days=1),
        observation_id="obs-twin-latest",
    )

    service = _monitoring_service(db_session)
    index_repo = service._reasoning_run_index_repository
    twin_service = DigitalTwinService(
        monitoring_service=service,
        cache=MemoryDigitalTwinCache(),
    )

    with patch.object(
        index_repo,
        "list",
        side_effect=AssertionError("digital twin must not scan all run indexes"),
    ):
        twin = twin_service.get_for_asset(target_asset)

    assert twin.latest_reasoning_run_id == "twin-run-latest"


def test_latest_semantics_unchanged_with_large_noise_corpus(
    db_session: Session,
) -> None:
    target_asset = "asset-semantic"
    for offset in range(4):
        _seed_minimal_run(
            db_session,
            run_id=f"semantic-run-{offset}",
            asset_id=target_asset,
            started_at=DEFAULT_TIMESTAMP + timedelta(minutes=offset),
            observation_id=f"obs-semantic-{offset}",
        )

    service = _monitoring_service(db_session)
    baseline_latest = service.get_latest_for_asset(target_asset)
    baseline_recommendation = service.get_recommendation(target_asset)
    assert baseline_latest is not None
    assert baseline_recommendation is not None

    _seed_noise_runs(db_session, asset_id="asset-noise-d", count=2500, start_index=0)

    noisy_latest = service.get_latest_for_asset(target_asset)
    noisy_recommendation = service.get_recommendation(target_asset)

    assert noisy_latest is not None
    assert noisy_recommendation is not None
    assert noisy_latest.run.id == baseline_latest.run.id
    assert noisy_latest.decision_plan.id == baseline_latest.decision_plan.id
    assert noisy_recommendation.title == baseline_recommendation.title
    assert noisy_recommendation.priority == baseline_recommendation.priority


def test_large_corpus_latest_and_digital_twin_complete_quickly(
    db_session: Session,
) -> None:
    target_asset = "asset-latency"
    _seed_noise_runs(db_session, asset_id="asset-noise-e", count=3000, start_index=0)
    _seed_minimal_run(
        db_session,
        run_id="latency-run-latest",
        asset_id=target_asset,
        started_at=DEFAULT_TIMESTAMP + timedelta(days=2),
        observation_id="obs-latency-latest",
    )

    service = _monitoring_service(db_session)
    twin_service = DigitalTwinService(
        monitoring_service=service,
        cache=MemoryDigitalTwinCache(),
    )

    latest_start = time.perf_counter()
    latest = service.get_latest_for_asset(target_asset)
    latest_elapsed = time.perf_counter() - latest_start

    twin_start = time.perf_counter()
    twin = twin_service.get_for_asset(target_asset)
    twin_elapsed = time.perf_counter() - twin_start

    assert latest is not None
    assert latest.run.id == "latency-run-latest"
    assert twin.latest_reasoning_run_id == "latency-run-latest"
    assert latest_elapsed < 1.0
    assert twin_elapsed < 2.0
