"""CLI entry point: `python -m backend.simulator.dataset.calibration`.

::

    python -m backend.simulator.dataset.calibration \\
        --features datasets/pem-faults-pilot-features \\
        --output datasets/pem-faults-pilot-calibration
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from backend.simulator.dataset.audit.loader import DatasetNotFoundError
from backend.simulator.dataset.calibration.generate import (
    CalibrationOutputExistsError,
    generate_calibration,
)
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
    CalibrationOutputExistsError,
    ManifestHashMismatchError,
    FeatureColumnOrderError,
    RowAlignmentError,
    SplitOverlapError,
    SourceDatasetNotFoundError,
)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    command = "python -m backend.simulator.dataset.calibration " + " ".join(
        sys.argv[1:] if argv is None else argv
    )

    try:
        result = generate_calibration(
            args.features,
            args.output,
            dataset_directory=args.dataset,
            overwrite=args.overwrite,
            generation_command=command,
        )
    except _KNOWN_ERRORS as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(f"calibration artifacts written to {result.output_directory}")
    print(
        f"selected: confidence_threshold={result.selected_confidence_threshold} "
        f"persistence_samples={result.selected_persistence_samples}"
    )
    print(
        f"test: balanced_accuracy(covered)={result.test_balanced_accuracy_covered:.3f} "
        f"coverage={result.test_coverage:.3f} "
        f"false_alarms_per_healthy_hour={result.test_false_alarms_per_healthy_hour:.3f}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
