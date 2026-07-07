import pytest

from odis.cli import main


@pytest.mark.parametrize(
    "scenario",
    ["heatwave", "stable", "oscillating", "csv", "fuel-cell"],
)
def test_demo_cli_dispatch_executes_scenarios(
    scenario: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["demo", scenario]) == 0
    capsys.readouterr()

