"""`SqlAlchemyAiFaultEvidenceRepository` specifications for the two new
read-model queries added in PR179.
"""

from __future__ import annotations

from collections.abc import Callable, Generator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from backend.app.domain.ai_fault_evidence import AiFaultEvidence
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

_ASSET_ID = "asset-repo-1"
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


def _evidence(
    *,
    evidence_id: str,
    investigation_id: str,
    observed_at: datetime,
    status: str = "OPEN",
    fault_class: str = "cooling_degradation",
) -> AiFaultEvidence:
    return AiFaultEvidence(
        id=evidence_id,
        source_event_id=evidence_id,
        asset_id=_ASSET_ID,
        observed_at=observed_at,
        alert_transition_type="confirmed",
        diagnosed_fault_class=fault_class,
        from_state="healthy",
        to_state=f"confirmed_{fault_class}",
        model_system_version="plant_alpha_fault_v1",
        model_hash="hash-a",
        policy_hash="policy-a",
        feature_schema_version="1.0",
        class_scores={"healthy": 0.1, fault_class: 0.9},
        maximum_score=0.9,
        evidence_items=({"label": "x", "value": 1.0, "detail": "y"},),
        investigation_id=investigation_id,
        investigation_status=status,  # type: ignore[arg-type]
        previous_diagnosed_fault_class=None,
        corroboration_result="corroborated",
        corroboration_rule_ids=("rule-1",),
        corroboration_notes="notes",
        recommendation=None,
        recorded_at=observed_at,
    )


def test_list_for_asset_grouped_by_investigation_counts_investigations_not_rows(
    session_factory: Callable[[], Session],
) -> None:
    """A multi-row investigation must count once, not once per row, so an
    older separate investigation isn't crowded out by `limit`."""
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        repository = SqlAlchemyAiFaultEvidenceRepository(uow.session)
        # Older investigation: a single row.
        repository.save(
            _evidence(
                evidence_id="evt-1",
                investigation_id="inv-1",
                observed_at=_T0,
                status="CLEARED",
            )
        )
        # Newer investigation: three lifecycle rows (confirmed, class_changed, cleared).
        repository.save(
            _evidence(
                evidence_id="evt-2",
                investigation_id="inv-2",
                observed_at=_T0 + timedelta(seconds=10),
            )
        )
        repository.save(
            _evidence(
                evidence_id="evt-3",
                investigation_id="inv-2",
                observed_at=_T0 + timedelta(seconds=20),
                fault_class="hydrogen_supply_issue",
            )
        )
        repository.save(
            _evidence(
                evidence_id="evt-4",
                investigation_id="inv-2",
                observed_at=_T0 + timedelta(seconds=30),
                status="CLEARED",
                fault_class="hydrogen_supply_issue",
            )
        )
        uow.commit()

    with SqlAlchemyUnitOfWork(session_factory) as uow:
        repository = SqlAlchemyAiFaultEvidenceRepository(uow.session)

        one = repository.list_for_asset_grouped_by_investigation(_ASSET_ID, limit=1)
        assert len(one) == 1
        assert one[0].investigation_id == "inv-2"
        assert one[0].id == "evt-4"  # the latest row of inv-2

        both = repository.list_for_asset_grouped_by_investigation(_ASSET_ID, limit=2)
        assert [e.investigation_id for e in both] == ["inv-2", "inv-1"]


def test_list_for_asset_grouped_by_investigation_empty_when_no_history(
    session_factory: Callable[[], Session],
) -> None:
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        repository = SqlAlchemyAiFaultEvidenceRepository(uow.session)
        result = repository.list_for_asset_grouped_by_investigation(
            "unknown-asset", limit=10
        )
    assert result == []


def test_list_for_investigation_returns_full_lifecycle_oldest_first(
    session_factory: Callable[[], Session],
) -> None:
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        repository = SqlAlchemyAiFaultEvidenceRepository(uow.session)
        repository.save(
            _evidence(evidence_id="evt-1", investigation_id="inv-1", observed_at=_T0)
        )
        repository.save(
            _evidence(
                evidence_id="evt-2",
                investigation_id="inv-1",
                observed_at=_T0 + timedelta(seconds=10),
                status="CLEARED",
            )
        )
        uow.commit()

    with SqlAlchemyUnitOfWork(session_factory) as uow:
        repository = SqlAlchemyAiFaultEvidenceRepository(uow.session)
        lifecycle = repository.list_for_investigation("inv-1")

    assert [e.id for e in lifecycle] == ["evt-1", "evt-2"]


def test_list_for_investigation_empty_for_unknown_id(
    session_factory: Callable[[], Session],
) -> None:
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        repository = SqlAlchemyAiFaultEvidenceRepository(uow.session)
        assert repository.list_for_investigation("does-not-exist") == []
