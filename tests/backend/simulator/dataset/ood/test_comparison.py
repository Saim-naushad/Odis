"""`MetricDelta` arithmetic (spec section 14, "Evaluation" — "ID/OOD
comparison calculations")."""

from __future__ import annotations

from backend.simulator.dataset.ood.comparison import MetricDelta


def test_absolute_and_relative_change() -> None:
    delta = MetricDelta(id_value=0.80, ood_value=0.60)
    assert delta.absolute_change is not None
    assert abs(delta.absolute_change - (-0.20)) < 1e-12
    assert delta.relative_change is not None
    assert abs(delta.relative_change - (-0.25)) < 1e-9


def test_none_values_propagate_as_none() -> None:
    delta = MetricDelta(id_value=None, ood_value=0.5)
    assert delta.absolute_change is None
    assert delta.relative_change is None

    delta2 = MetricDelta(id_value=0.5, ood_value=None)
    assert delta2.absolute_change is None
    assert delta2.relative_change is None


def test_relative_change_undefined_for_near_zero_id_value() -> None:
    delta = MetricDelta(id_value=0.0, ood_value=5.0)
    assert delta.absolute_change == 5.0
    assert delta.relative_change is None


def test_to_json_dict_round_trips_values() -> None:
    delta = MetricDelta(id_value=1.0, ood_value=2.0)
    data = delta.to_json_dict()
    assert data["id"] == 1.0
    assert data["ood"] == 2.0
    assert data["absolute_change"] == 1.0
    assert data["relative_change"] == 1.0
