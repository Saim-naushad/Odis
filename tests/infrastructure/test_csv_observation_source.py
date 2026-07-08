from datetime import UTC, datetime
from pathlib import Path

import pytest

from domain.value_objects.measurement_type import MeasurementType
from infrastructure.sources.csv_observation_source import CsvObservationSource
from tests.builders import build_observation

_HEADER = "id,asset_id,measurement_type,value,unit,timestamp\n"


def _write_csv(path: Path, *rows: str) -> None:
    path.write_text(_HEADER + "".join(rows), encoding="utf-8")


def test_empty_file_returns_empty_tuple(tmp_path: Path) -> None:
    csv_path = tmp_path / "observations.csv"
    csv_path.write_text(_HEADER, encoding="utf-8")

    source = CsvObservationSource(csv_path)

    assert source.read() == ()


def test_one_observation(tmp_path: Path) -> None:
    csv_path = tmp_path / "observations.csv"
    _write_csv(
        csv_path,
        "obs-1,asset-1,temperature,32.5,celsius,2026-01-01T12:00:00+00:00\n",
    )

    source = CsvObservationSource(csv_path)
    observations = source.read()

    assert observations == (
        build_observation(
            id="obs-1",
            asset_id="asset-1",
            measurement_type=MeasurementType(name="temperature"),
            value=32.5,
            unit="celsius",
            timestamp=datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
        ),
    )


def test_multiple_observations_preserve_order(tmp_path: Path) -> None:
    csv_path = tmp_path / "observations.csv"
    _write_csv(
        csv_path,
        "obs-1,asset-1,temperature,10.0,celsius,2026-01-01T12:00:00+00:00\n",
        "obs-2,asset-1,temperature,20.0,celsius,2026-01-01T13:00:00+00:00\n",
        "obs-3,asset-1,temperature,30.0,celsius,2026-01-01T14:00:00+00:00\n",
    )

    source = CsvObservationSource(csv_path)
    observations = source.read()

    assert [observation.id for observation in observations] == [
        "obs-1",
        "obs-2",
        "obs-3",
    ]
    assert [observation.value for observation in observations] == [10.0, 20.0, 30.0]


def test_malformed_row_raises_value_error(tmp_path: Path) -> None:
    csv_path = tmp_path / "observations.csv"
    _write_csv(
        csv_path,
        "obs-1,asset-1,temperature,not-a-number,celsius,2026-01-01T12:00:00+00:00\n",
    )

    source = CsvObservationSource(csv_path)

    with pytest.raises(ValueError, match="malformed row 2"):
        source.read()


def test_repeated_reads_return_equivalent_observations(tmp_path: Path) -> None:
    csv_path = tmp_path / "observations.csv"
    _write_csv(
        csv_path,
        "obs-1,asset-1,temperature,10.0,celsius,2026-01-01T12:00:00+00:00\n",
        "obs-2,asset-1,temperature,20.0,celsius,2026-01-01T13:00:00+00:00\n",
    )

    source = CsvObservationSource(csv_path)

    first_read = source.read()
    second_read = source.read()

    assert first_read == second_read
    assert first_read is not second_read
