"""Reasoning artifact persistence specifications."""

from collections.abc import Generator

import pytest
from sqlalchemy.orm import Session

from application.reasoning_run import ReasoningRun
from application.reasoning_run_index import ReasoningRunIndex
from application.reasoning_trace import ReasoningTrace, TraceStep
from application.structured_assessment import StructuredAssessment
from backend.app.infrastructure.config.settings import Settings
from backend.app.infrastructure.database import models as _models  # noqa: F401
from backend.app.infrastructure.database.base import Base
from backend.app.infrastructure.database.mappers.reasoning_trace import (
    reasoning_trace_to_domain,
    reasoning_trace_to_model,
)
from backend.app.infrastructure.database.mappers.structured_assessment import (
    structured_assessment_to_domain,
    structured_assessment_to_model,
)
from backend.app.infrastructure.database.session import (
    create_db_engine,
    create_session_factory,
)
from backend.app.infrastructure.repositories.reasoning_run_repository import (
    SqlAlchemyReasoningRunRepository,
)
from backend.app.infrastructure.repositories.reasoning_trace_repository import (
    SqlAlchemyReasoningTraceRepository,
)
from backend.app.infrastructure.repositories.structured_assessment_repository import (
    SqlAlchemyStructuredAssessmentRepository,
)
from domain.value_objects.trend_direction import TrendDirection
from domain.value_objects.variation_level import VariationLevel
from tests.builders import DEFAULT_TIMESTAMP


@pytest.fixture
def sqlite_settings() -> Settings:
    return Settings(database_url="sqlite://")


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


def _persist_run(db_session: Session, run_id: str = "run-1") -> ReasoningRun:
    run = ReasoningRun(id=run_id, started_at=DEFAULT_TIMESTAMP)
    SqlAlchemyReasoningRunRepository(db_session).save(run)
    return run


def test_structured_assessment_round_trip_mapping() -> None:
    assessment = StructuredAssessment(
        trend_direction=TrendDirection.INCREASING,
        variation_level=VariationLevel.LOW,
        has_correlations=True,
        has_contradictions=False,
        has_unexpected_expectations=False,
        has_indeterminate_expectations=True,
    )

    model = structured_assessment_to_model("run-map", assessment)
    domain = structured_assessment_to_domain(model)

    assert domain == assessment


def test_reasoning_trace_round_trip_mapping() -> None:
    trace = ReasoningTrace(
        steps=(
            TraceStep(name="Trend Detected", description="Trend was detected."),
            TraceStep(name="Situation Assessed", description="Situation was assessed."),
        )
    )

    model = reasoning_trace_to_model("run-map", trace)
    domain = reasoning_trace_to_domain(model)

    assert domain == trace


def test_structured_assessment_repository_persists_assessment(
    db_session: Session,
) -> None:
    run = _persist_run(db_session)
    repository = SqlAlchemyStructuredAssessmentRepository(db_session)
    assessment = StructuredAssessment(
        trend_direction=TrendDirection.STABLE,
        variation_level=VariationLevel.HIGH,
        has_correlations=False,
        has_contradictions=False,
        has_unexpected_expectations=False,
        has_indeterminate_expectations=False,
    )

    repository.save(run.id, assessment)

    assert repository.get_by_run_id(run.id) == assessment


def test_reasoning_trace_repository_persists_trace(db_session: Session) -> None:
    run = _persist_run(db_session, run_id="run-trace")
    repository = SqlAlchemyReasoningTraceRepository(db_session)
    trace = ReasoningTrace(
        steps=(TraceStep(name="Observations Loaded", description="Loaded."),)
    )

    repository.save(run.id, trace)

    assert repository.get_by_run_id(run.id) == trace


def test_reasoning_run_index_links_artifacts(db_session: Session) -> None:
    from backend.app.infrastructure.repositories.reasoning_run_index_repository import (
        SqlAlchemyReasoningRunIndexRepository,
    )

    _persist_run(db_session, run_id="run-index")
    index = ReasoningRunIndex(
        run_id="run-index",
        observation_ids=("obs-1", "obs-2"),
        situation_id="situation-1",
        context_id="context-1",
        plan_id="plan-1",
        action_id="action-1",
        outcome_id="outcome-1",
        asset_id="asset-1",
    )
    repository = SqlAlchemyReasoningRunIndexRepository(db_session)

    repository.save(index)

    assert repository.get("run-index") == index
