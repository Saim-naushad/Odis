import csv
from datetime import datetime
from pathlib import Path

from domain.entities.observation import Observation
from domain.value_objects.measurement_type import MeasurementType

_EXPECTED_COLUMNS = 6


class CsvObservationSource:
    def __init__(self, path: Path | str) -> None:
        self._path = Path(path)

    def read(self) -> tuple[Observation, ...]:
        with self._path.open(newline="") as file:
            reader = csv.reader(file)
            try:
                next(reader)
            except StopIteration:
                return ()

            observations: list[Observation] = []
            for row_number, row in enumerate(reader, start=2):
                observations.append(self._parse_row(row, row_number))

            return tuple(observations)

    def _parse_row(self, row: list[str], row_number: int) -> Observation:
        if len(row) != _EXPECTED_COLUMNS:
            raise ValueError(
                f"malformed row {row_number}: expected {_EXPECTED_COLUMNS} columns, "
                f"got {len(row)}"
            )

        (
            observation_id,
            asset_id,
            measurement_type_name,
            value_text,
            unit,
            timestamp_text,
        ) = row

        try:
            value = float(value_text)
        except ValueError as exc:
            raise ValueError(
                f"malformed row {row_number}: invalid value {value_text!r}"
            ) from exc

        try:
            timestamp = datetime.fromisoformat(timestamp_text)
        except ValueError as exc:
            raise ValueError(
                f"malformed row {row_number}: invalid timestamp {timestamp_text!r}"
            ) from exc

        return Observation(
            id=observation_id,
            asset_id=asset_id,
            timestamp=timestamp,
            measurement_type=MeasurementType(name=measurement_type_name),
            value=value,
            unit=unit,
        )
