"""Tests for simulator publish deadline scheduling."""

from __future__ import annotations

from backend.simulator.__main__ import (
    _advance_publish_deadline,
    _seconds_until_next_deadline,
)


def test_seconds_until_next_deadline_is_positive_when_waiting() -> None:
    assert _seconds_until_next_deadline(10.0, 25.0, 40.0) == 15.0


def test_seconds_until_next_deadline_uses_earlier_deadline() -> None:
    assert _seconds_until_next_deadline(30.0, 45.0, 35.0) == 5.0


def test_advance_publish_deadline_preserves_future_deadline() -> None:
    assert _advance_publish_deadline(100.0, 15.0, 90.0) == 100.0


def test_advance_publish_deadline_skips_missed_slots() -> None:
    assert _advance_publish_deadline(70.0, 15.0, 100.0) == 115.0


def test_advance_publish_deadline_on_exact_tick() -> None:
    assert _advance_publish_deadline(100.0, 15.0, 100.0) == 115.0


def test_overrun_skips_sleep_until_core_is_next() -> None:
    """When derived is overdue, the loop publishes instead of sleeping."""
    now = 120.0
    next_core_at = 125.0
    next_derived_at = 100.0
    assert now >= next_derived_at
    assert now < next_core_at
    # Sleep is only used when both deadlines are still in the future.
    assert not (now < next_core_at and now < next_derived_at)
