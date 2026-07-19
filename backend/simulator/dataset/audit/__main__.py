"""CLI entry point: `python -m backend.simulator.dataset.audit`.

::

    python -m backend.simulator.dataset.audit \\
        --dataset datasets/pem-faults-pilot \\
        --output datasets/pem-faults-pilot-audit
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from backend.simulator.dataset.audit.loader import DatasetNotFoundError
from backend.simulator.dataset.audit.report import run_audit


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--no-plots",
        action="store_true",
        help="Skip plot generation even if the dataset-analysis extra is installed.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)

    try:
        result = run_audit(
            args.dataset,
            args.output,
            generate_plots_flag=not args.no_plots,
        )
    except DatasetNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    counts = {"blocking": 0, "high": 0, "medium": 0, "low": 0}
    for finding in result.findings:
        counts[finding.severity] += 1

    print(f"quality report written to {result.report_path}")
    print(f"summary written to {result.summary_path}")
    print(
        f"findings: blocking={counts['blocking']} high={counts['high']} "
        f"medium={counts['medium']} low={counts['low']}"
    )
    print(f"verdict: {result.verdict}")

    return result.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
