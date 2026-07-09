"""Unit of work specifications."""

from __future__ import annotations

from unittest.mock import MagicMock

from sqlalchemy.orm import Session

from backend.app.infrastructure.persistence.sqlalchemy_unit_of_work import (
    SqlAlchemyUnitOfWork,
)


def test_unit_of_work_commit_calls_session_commit() -> None:
    session = MagicMock(spec=Session)
    uow = SqlAlchemyUnitOfWork(lambda: session)

    uow.commit()

    session.commit.assert_called_once_with()


def test_unit_of_work_rollback_calls_session_rollback() -> None:
    session = MagicMock(spec=Session)
    uow = SqlAlchemyUnitOfWork(lambda: session)

    uow.rollback()

    session.rollback.assert_called_once_with()


def test_unit_of_work_close_calls_session_close() -> None:
    session = MagicMock(spec=Session)
    uow = SqlAlchemyUnitOfWork(lambda: session)

    uow.close()

    session.close.assert_called_once_with()


def test_unit_of_work_context_manager_commits_and_closes_on_success() -> None:
    session = MagicMock(spec=Session)

    with SqlAlchemyUnitOfWork(lambda: session):
        pass

    session.commit.assert_called_once_with()
    session.close.assert_called_once_with()
    session.rollback.assert_not_called()


def test_unit_of_work_context_manager_rolls_back_and_closes_on_error() -> None:
    session = MagicMock(spec=Session)

    try:
        with SqlAlchemyUnitOfWork(lambda: session):
            raise RuntimeError("boom")
    except RuntimeError:
        pass

    session.rollback.assert_called_once_with()
    session.close.assert_called_once_with()


def test_unit_of_work_context_manager_does_not_double_commit() -> None:
    session = MagicMock(spec=Session)

    with SqlAlchemyUnitOfWork(lambda: session) as uow:
        uow.commit()

    session.commit.assert_called_once_with()
    session.close.assert_called_once_with()

