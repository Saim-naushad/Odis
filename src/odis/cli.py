from __future__ import annotations

import argparse
from collections.abc import Callable, Sequence

DEMO_SCENARIOS = ("heatwave", "stable", "oscillating", "csv", "all")


def dispatch_demo(scenario: str) -> None:
    from odis.examples import (
        csv_demo,
        heatwave_demo,
        oscillating_operations_demo,
        run_demo,
        stable_operations_demo,
    )

    runners: dict[str, Callable[[], object]] = {
        "heatwave": heatwave_demo.main,
        "stable": stable_operations_demo.main,
        "oscillating": oscillating_operations_demo.main,
        "csv": csv_demo.main,
        "all": run_demo.main,
    }
    runners[scenario]()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="odis",
        description="ODIS Operational Reasoning Platform",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Commands:\n"
            "  demo heatwave      Rising temperature walkthrough\n"
            "  demo stable        Stable operations walkthrough\n"
            "  demo oscillating   Oscillating flow-rate walkthrough\n"
            "  demo csv           Run reasoning from a real CSV file\n"
            "  demo all           Run all scenarios with replay summaries"
        ),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    demo_parser = subparsers.add_parser(
        "demo",
        help="run an operational walkthrough demonstration",
    )
    demo_parser.add_argument(
        "scenario",
        choices=DEMO_SCENARIOS,
        help="which demonstration to run",
    )

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.command == "demo":
        dispatch_demo(args.scenario)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
