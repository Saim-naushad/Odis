from unittest.mock import patch

import pytest

from odis.cli import DEMO_SCENARIOS, main


def test_help_exits_successfully() -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["--help"])

    assert exc_info.value.code == 0


def test_demo_help_exits_successfully() -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["demo", "--help"])

    assert exc_info.value.code == 0


@pytest.mark.parametrize("scenario", DEMO_SCENARIOS)
def test_valid_demo_commands_dispatch(scenario: str) -> None:
    with patch("odis.cli.dispatch_demo") as mock_dispatch:
        assert main(["demo", scenario]) == 0

    mock_dispatch.assert_called_once_with(scenario)


def test_unknown_demo_name_produces_helpful_error(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["demo", "unknown"])

    assert exc_info.value.code != 0
    captured = capsys.readouterr()
    assert "invalid choice" in captured.err.lower()


def test_fuel_cell_demo_executes_successfully(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["demo", "fuel-cell"]) == 0
    captured = capsys.readouterr()
    assert "FuelCellOperationalProfile" in captured.out
