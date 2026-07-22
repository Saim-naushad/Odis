"""`FaultInvestigationService` specifications (PR179 read-model composer)."""

from __future__ import annotations

from collections.abc import Callable, Generator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from backend.app.application.fault_investigation_service import (
    FaultInvestigationService,
)
from backend.app.domain.ai_fault_evidence import AiFaultEvidence, FaultRecommendation
from backend.app.infrastructure.config.settings import Settings
from backend.app.infrastructure.database import models as _models  # noqa: F401
from backend.app.infrastructure.database.base import Base
from backend.app.infrastructure.database.session import (
    create_db_engine,
    create_session_factory,
)
from backend.app.infrastructure.persistence.sqlalchemy_unit_of_work import (
    SqlAlchemyUnitOfWork,
)
from backend.app.infrastructure.repositories.ai_fault_evidence_repository import (
    SqlAlchemyAiFaultEvidenceRepository,
)
from backend.app.infrastructure.repositories.observation_repository import (
    SqlAlchemyObservationRepository,
)
from domain.entities.observation import Observation
from domain.value_objects.measurement_type import MeasurementType

_ASSET_ID = "asset-svc-1"
_T0 = datetime(2026, 1, 1, tzinfo=UTC)


@pytest.fixture
def sqlite_settings() -> Settings:
    return Settings(database_url="sqlite://")


@pytest.fixture
def session_factory(
    sqlite_settings: Settings,
) -> Generator[Callable[[], Session], None, None]:
    engine = create_db_engine(sqlite_settings)
    Base.metadata.create_all(engine)
    factory = create_session_factory(engine)
    try:
        yield factory
    finally:
        engine.dispose()


def _recommendation(
    supporting_observation_ids: tuple[str, ...] = (),
) -> FaultRecommendation:
    return FaultRecommendation(
        id="rec-1",
        status="produced",
        category="investigate",
        urgency="ELEVATED",
        action_summary="Inspect cooling subsystem",
        reason="Deterministic telemetry corroborated the alert.",
        supporting_rule_ids=("rule-1",),
        supporting_observation_ids=supporting_observation_ids,
        recommended_steps=("Check pump",),
        limitations="Automated inspection cannot substitute for a manual check.",
    )


def _evidence(
    *,
    evidence_id: str,
    investigation_id: str,
    observed_at: datetime,
    status: str = "OPEN",
    recommendation: FaultRecommendation | None = None,
) -> AiFaultEvidence:
    return AiFaultEvidence(
        id=evidence_id,
        source_event_id=evidence_id,
        asset_id=_ASSET_ID,
        observed_at=observed_at,
        alert_transition_type="confirmed",
        diagnosed_fault_class="cooling_degradation",
        from_state="healthy",
        to_state="confirmed_cooling_degradation",
        model_system_version="plant_alpha_fault_v1",
        model_hash="hash-a",
        policy_hash="policy-a",
        feature_schema_version="1.0",
        class_scores={"healthy": 0.1, "cooling_degradation": 0.9},
        maximum_score=0.9,
        evidence_items=({"label": "x", "value": 1.0, "detail": "y"},),
        investigation_id=investigation_id,
        investigation_status=status,  # type: ignore[arg-type]
        previous_diagnosed_fault_class=None,
        corroboration_result="corroborated",
        corroboration_rule_ids=("rule-1",),
        corroboration_notes="notes",
        recommendation=recommendation,
        recorded_at=observed_at,
    )


def test_get_active_for_asset_is_none_when_no_history(
    session_factory: Callable[[], Session],
) -> None:
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        service = FaultInvestigationService(
            SqlAlchemyAiFaultEvidenceRepository(uow.session),
            SqlAlchemyObservationRepository(uow.session),
        )
        assert service.get_active_for_asset(_ASSET_ID) is None


def test_get_active_for_asset_is_none_when_latest_is_cleared(
    session_factory: Callable[[], Session],
) -> None:
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        evidence_repository = SqlAlchemyAiFaultEvidenceRepository(uow.session)
        evidence_repository.save(
            _evidence(evidence_id="evt-1", investigation_id="inv-1", observed_at=_T0)
        )
        evidence_repository.save(
            _evidence(
                evidence_id="evt-2",
                investigation_id="inv-1",
                observed_at=_T0 + timedelta(seconds=10),
                status="CLEARED",
            )
        )
        uow.commit()

    with SqlAlchemyUnitOfWork(session_factory) as uow:
        service = FaultInvestigationService(
            SqlAlchemyAiFaultEvidenceRepository(uow.session),
            SqlAlchemyObservationRepository(uow.session),
        )
        assert service.get_active_for_asset(_ASSET_ID) is None


def test_get_active_for_asset_returns_the_open_investigation(
    session_factory: Callable[[], Session],
) -> None:
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        evidence_repository = SqlAlchemyAiFaultEvidenceRepository(uow.session)
        evidence_repository.save(
            _evidence(evidence_id="evt-1", investigation_id="inv-1", observed_at=_T0)
        )
        uow.commit()

    with SqlAlchemyUnitOfWork(session_factory) as uow:
        service = FaultInvestigationService(
            SqlAlchemyAiFaultEvidenceRepository(uow.session),
            SqlAlchemyObservationRepository(uow.session),
        )
        active = service.get_active_for_asset(_ASSET_ID)
        assert active is not None
        assert active.id == "evt-1"


def test_list_history_for_asset_passes_through_grouped_query(
    session_factory: Callable[[], Session],
) -> None:
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        evidence_repository = SqlAlchemyAiFaultEvidenceRepository(uow.session)
        evidence_repository.save(
            _evidence(evidence_id="evt-1", investigation_id="inv-1", observed_at=_T0)
        )
        evidence_repository.save(
            _evidence(
                evidence_id="evt-2",
                investigation_id="inv-2",
                observed_at=_T0 + timedelta(seconds=10),
            )
        )
        uow.commit()

    with SqlAlchemyUnitOfWork(session_factory) as uow:
        service = FaultInvestigationService(
            SqlAlchemyAiFaultEvidenceRepository(uow.session),
            SqlAlchemyObservationRepository(uow.session),
        )
        history = service.list_history_for_asset(_ASSET_ID, limit=10)
        assert [e.investigation_id for e in history] == ["inv-2", "inv-1"]


def test_get_investigation_returns_empty_list_for_unknown_id(
    session_factory: Callable[[], Session],
) -> None:
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        service = FaultInvestigationService(
            SqlAlchemyAiFaultEvidenceRepository(uow.session),
            SqlAlchemyObservationRepository(uow.session),
        )
        assert service.get_investigation("does-not-exist") == []


def test_resolve_supporting_evidence_is_empty_without_a_recommendation(
    session_factory: Callable[[], Session],
) -> None:
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        service = FaultInvestigationService(
            SqlAlchemyAiFaultEvidenceRepository(uow.session),
            SqlAlchemyObservationRepository(uow.session),
        )
        evidence = _evidence(
            evidence_id="evt-1", investigation_id="inv-1", observed_at=_T0
        )
        assert service.resolve_supporting_evidence(evidence) == []


def test_resolve_supporting_evidence_is_bounded_and_skips_missing_ids(
    session_factory: Callable[[], Session],
) -> None:
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        observation_repository = SqlAlchemyObservationRepository(uow.session)
        for i in range(10):
            observation_repository.save(
                Observation(
                    id=f"obs-{i}",
                    asset_id=_ASSET_ID,
                    timestamp=_T0,
                    measurement_type=MeasurementType(name="stack_temperature"),
                    value=float(i),
                    unit="celsius",
                )
            )
        uow.commit()

    supporting_ids = (*(f"obs-{i}" for i in range(10)), "obs-missing")
    evidence = _evidence(
        evidence_id="evt-1",
        investigation_id="inv-1",
        observed_at=_T0,
        recommendation=_recommendation(supporting_ids),
    )

    with SqlAlchemyUnitOfWork(session_factory) as uow:
        service = FaultInvestigationService(
            SqlAlchemyAiFaultEvidenceRepository(uow.session),
            SqlAlchemyObservationRepository(uow.session),
        )
        resolved = service.resolve_supporting_evidence(evidence, limit=8)

    assert len(resolved) == 8
    assert [o.id for o in resolved] == [f"obs-{i}" for i in range(8)]
