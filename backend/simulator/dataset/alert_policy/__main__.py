"""CLI entry point: `python -m backend.simulator.dataset.alert_policy`.

::

    python -m backend.simulator.dataset.alert_policy \\
        --features datasets/pem-faults-pilot-features \\
        --output datasets/pem-faults-pilot-alert-policy
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from backend.simulator.dataset.alert_policy.generate import (
    AlertPolicyOutputExistsError,
    generate_alert_policy,
)
from backend.simulator.dataset.audit.loader import DatasetNotFoundError
from backend.simulator.dataset.models.data import (
    FeatureColumnOrderError,
    ManifestHashMismatchError,
    RowAlignmentError,
    SourceDatasetNotFoundError,
    SplitOverlapError,
)


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--features", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--dataset",
        type=Path,
        default=None,
        help=(
            "Source dataset directory (runs.parquet/ground_truth.parquet), for "
            "evaluation-only metadata. Defaults to feature_manifest.json's "
            "recorded source_dataset.directory."
        ),
    )
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args(argv)


_KNOWN_ERRORS = (
    DatasetNotFoundError,
    AlertPolicyOutputExistsError,
    ManifestHashMismatchError,
    FeatureColumnOrderError,
    RowAlignmentError,
    SplitOverlapError,
    SourceDatasetNotFoundError,
)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    command = "python -m backend.simulator.dataset.alert_policy " + " ".join(
        sys.argv[1:] if argv is None else argv
    )

    try:
        result = generate_alert_policy(
            args.features,
            args.output,
            dataset_directory=args.dataset,
            overwrite=args.overwrite,
            generation_command=command,
        )
    except _KNOWN_ERRORS as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(f"alert policy artifacts written to {result.output_directory}")
    if result.selected_entry_probability is not None:
        print(
            f"selected: entry_probability={result.selected_entry_probability} "
            f"entry_persistence={result.selected_entry_persistence} "
            f"healthy_exit_probability={result.selected_healthy_exit_probability} "
            f"exit_persistence={result.selected_exit_persistence}"
        )
        print(
            f"test: false_alert_events_per_healthy_hour="
            f"{result.test_false_alert_events_per_healthy_hour:.3f} "
            f"correct_class_missed_runs={result.test_correct_class_missed_run_count}"
        )
    else:
        print("no policy was selected — see alert_evaluation_report.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
