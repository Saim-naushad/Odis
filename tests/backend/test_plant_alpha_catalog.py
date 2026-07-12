from __future__ import annotations

from backend.app.application.plant_alpha_catalog import (
    DEFAULT_PLANT_ALPHA_CATALOG,
    PlantAlphaCatalog,
)
from domain.entities.asset import Asset
from domain.value_objects.location import Location


def test_known_asset_returns_realistic_identity() -> None:
    asset = DEFAULT_PLANT_ALPHA_CATALOG.get("fuel-cell-stack-01")

    assert asset is not None
    assert asset.id == "fuel-cell-stack-01"
    assert asset.name == "PEM Fuel Cell Stack 01"
    assert asset.type == "PEM Fuel Cell Stack"
    assert asset.location.identifier == "North Production Line"


def test_all_four_plant_alpha_stacks_are_known() -> None:
    known_ids = {
        "fuel-cell-stack-01",
        "fuel-cell-stack-02",
        "fuel-cell-stack-03",
        "fuel-cell-stack-04",
    }
    for asset_id in known_ids:
        assert DEFAULT_PLANT_ALPHA_CATALOG.get(asset_id) is not None


def test_unknown_asset_returns_none() -> None:
    assert DEFAULT_PLANT_ALPHA_CATALOG.get("not-a-real-asset") is None


def test_catalog_is_deterministic_across_calls() -> None:
    first = DEFAULT_PLANT_ALPHA_CATALOG.get("fuel-cell-stack-02")
    second = DEFAULT_PLANT_ALPHA_CATALOG.get("fuel-cell-stack-02")

    assert first == second


def test_custom_fleet_can_be_injected() -> None:
    custom = Asset(
        id="test-asset",
        name="Test Asset",
        type="test",
        location=Location(identifier="test-site"),
    )
    catalog = PlantAlphaCatalog(fleet={"test-asset": custom})

    assert catalog.get("test-asset") == custom
    assert catalog.get("fuel-cell-stack-01") is None
