"""Static identity catalog for the Plant Alpha fuel-cell fleet.

Plant Alpha operates a fixed set of four PEM fuel-cell stacks. This catalog
is the single place that owns their operator-facing identity (name, type,
location) as fully constructed `Asset` domain objects. It is static and
deterministic: no I/O, no mutable state, no persistence.
"""

from __future__ import annotations

from domain.entities.asset import Asset
from domain.value_objects.location import Location

_FLEET: dict[str, Asset] = {
    "fuel-cell-stack-01": Asset(
        id="fuel-cell-stack-01",
        name="PEM Fuel Cell Stack 01",
        type="PEM Fuel Cell Stack",
        location=Location(identifier="North Production Line"),
    ),
    "fuel-cell-stack-02": Asset(
        id="fuel-cell-stack-02",
        name="PEM Fuel Cell Stack 02",
        type="PEM Fuel Cell Stack",
        location=Location(identifier="North Production Line"),
    ),
    "fuel-cell-stack-03": Asset(
        id="fuel-cell-stack-03",
        name="PEM Fuel Cell Stack 03",
        type="PEM Fuel Cell Stack",
        location=Location(identifier="South Production Line"),
    ),
    "fuel-cell-stack-04": Asset(
        id="fuel-cell-stack-04",
        name="PEM Fuel Cell Stack 04",
        type="PEM Fuel Cell Stack",
        location=Location(identifier="South Production Line"),
    ),
}


class PlantAlphaCatalog:
    """Looks up known Plant Alpha assets by id.

    Returns the immutable `Asset` domain entity directly; callers do not
    need to know how the fleet metadata is stored.
    """

    def __init__(self, fleet: dict[str, Asset] | None = None) -> None:
        self._fleet = fleet if fleet is not None else _FLEET

    def get(self, asset_id: str) -> Asset | None:
        """Return the known Asset for asset_id, or None if unrecognized."""
        return self._fleet.get(asset_id)


DEFAULT_PLANT_ALPHA_CATALOG = PlantAlphaCatalog()
