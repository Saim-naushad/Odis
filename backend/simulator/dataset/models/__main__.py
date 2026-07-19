"""CLI entry point: `python -m backend.simulator.dataset.models`.

::

    python -m backend.simulator.dataset.models \\
        --features datasets/pem-faults-pilot-features \\
        --output datasets/pem-faults-pilot-models
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from backend.simulator.dataset.audit.loader import DatasetNotFoundError
from backend.simulator.dataset.models.data import (
    FeatureColumnOrderError,
    ManifestHashMismatchError,
    RowAlignmentError,
    SourceDatasetNotFoundError,
    SplitOverlapError,
)
from backend.simulator.dataset.models.generate import (
    ModelOutputExistsError,
    generate_models,
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
    ModelOutputExistsError,
    ManifestHashMismatchError,
    FeatureColumnOrderError,
    RowAlignmentError,
    SplitOverlapError,
    SourceDatasetNotFoundError,
)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    command = "python -m backend.simulator.dataset.models " + " ".join(
        sys.argv[1:] if argv is None else argv
    )

    try:
        result = generate_models(
            args.features,
            args.output,
            dataset_directory=args.dataset,
            overwrite=args.overwrite,
            generation_command=command,
        )
    except _KNOWN_ERRORS as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(f"models written to {result.output_directory}")
    print(
        f"selected: {result.selected_model_type} / {result.selected_feature_group} "
        f"(validation balanced accuracy={result.validation_balanced_accuracy:.3f}, "
        f"test balanced accuracy={result.test_balanced_accuracy:.3f})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
