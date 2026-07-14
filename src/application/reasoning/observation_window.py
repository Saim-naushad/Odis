from __future__ import annotations

from collections.abc import Sequence

from domain.entities.observation import Observation


def bound_recent_observations(
    observations: Sequence[Observation],
    *,
    window: int,
) -> tuple[Observation, ...]:
    """Keep each measurement type's `window` most-recent observations.

    Bounds per measurement type, not a flat cap across the mixed-type
    sequence: derived measurements publish far less often than core ones, so
    a flat row cap would make the per-type slice size depend on how many
    derived samples happened to land inside the raw window at any given
    moment — unpredictable, and not what "recent history for this signal"
    should mean. Windowing per type keeps the slice size for any given
    measurement type deterministic regardless of what else was observed
    alongside it.

    Returned observations stay ordered by `(timestamp, id)` across the whole
    sequence, not grouped-by-type-then-concatenated: primary-measurement
    selection can depend on which observation sorts first, so scrambling
    order here could silently change which type ends up primary.
    """
    if window <= 0:
        raise ValueError("window must be > 0")

    by_type: dict[object, list[Observation]] = {}
    for observation in observations:
        by_type.setdefault(observation.measurement_type, []).append(observation)

    kept_ids: set[str] = set()
    for type_observations in by_type.values():
        type_observations.sort(
            key=lambda observation: (observation.timestamp, observation.id)
        )
        for observation in type_observations[-window:]:
            kept_ids.add(observation.id)

    ordered = sorted(
        observations, key=lambda observation: (observation.timestamp, observation.id)
    )
    return tuple(observation for observation in ordered if observation.id in kept_ids)
