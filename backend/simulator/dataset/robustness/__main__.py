"""CLI entry point: `python -m backend.simulator.dataset.robustness`.

::

    python -m backend.simulator.dataset.robustness \\
        --original-models datasets/pem-faults-pilot-models \\
        --robust-models datasets/pem-faults-robust-training-v1-models \\
        --robust-features datasets/pem-faults-robust-training-v1-features \\
        --robust-dataset datasets/pem-faults-robust-training-v1 \\
        --pilot-features datasets/pem-faults-pilot-features \\
        --pilot-dataset datasets/pem-faults-pilot \\
        --cohort high_load=DIR/shift-high-load-features:DIR/shift-high-load \\
        --cohort hot_start=DIR/shift-hot-start-features:DIR/shift-hot-start \\
        --cohort late_onset=DIR/shift-late-onset-features:DIR/shift-late-onset \\
        --cohort high_noise=DIR/shift-high-noise-features:DIR/shift-high-noise \\
        --cohort combined_ood_v1=DIR/ood-v1-features:DIR/ood-v1 \\
        --output datasets/pem-faults-robust-training-v1-comparison

(each ``--cohort`` value's ``DIR`` is ``datasets/pem-faults-``; spelled out
here only to keep this docstring's lines under the repo's line-length limit)
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from backend.simulator.dataset.models.data import (
    FeatureColumnOrderError,
    ManifestHashMismatchError,
    NonFiniteFeatureValueError,
    RowAlignmentError,
    SourceDatasetNotFoundError,
    SplitOverlapError,
)
from backend.simulator.dataset.robustness.artifacts import (
    ArtifactNotFoundError,
    IncompatibleArtifactError,
)
from backend.simulator.dataset.robustness.generate import (
    CohortDataset,
    RobustnessOutputExistsError,
    run_robustness_comparison,
)

_KNOWN_ERRORS = (
    ArtifactNotFoundError,
    IncompatibleArtifactError,
    RobustnessOutputExistsError,
    ManifestHashMismatchError,
    FeatureColumnOrderError,
    RowAlignmentError,
    SplitOverlapError,
    SourceDatasetNotFoundError,
    NonFiniteFeatureValueError,
)


def _parse_cohort(value: str) -> tuple[str, CohortDataset]:
    name, _, paths = value.partition("=")
    features, _, dataset = paths.partition(":")
    if not name or not features:
        raise argparse.ArgumentTypeError(
            f"--cohort must be NAME=FEATURES_DIR[:DATASET_DIR], got {value!r}"
        )
    return name, CohortDataset(
        features_dir=Path(features), dataset_dir=Path(dataset) if dataset else None
    )


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original-models", required=True, type=Path)
    parser.add_argument("--robust-models", required=True, type=Path)
    parser.add_argument("--robust-features", required=True, type=Path)
    parser.add_argument("--robust-dataset", required=True, type=Path)
    parser.add_argument("--pilot-features", required=True, type=Path)
    parser.add_argument("--pilot-dataset", required=True, type=Path)
    parser.add_argument(
        "--cohort",
        action="append",
        required=True,
        type=_parse_cohort,
        dest="cohorts",
        help="NAME=FEATURES_DIR[:DATASET_DIR], repeatable — one per external "
        "cohort (high_load, hot_start, late_onset, high_noise, combined_ood_v1)",
    )
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    command = "python -m backend.simulator.dataset.robustness " + " ".join(
        sys.argv[1:] if argv is None else argv
    )

    try:
        result = run_robustness_comparison(
            original_models_dir=args.original_models,
            robust_models_dir=args.robust_models,
            robust_features_dir=args.robust_features,
            robust_dataset_dir=args.robust_dataset,
            pilot_features_dir=args.pilot_features,
            pilot_dataset_dir=args.pilot_dataset,
            external_cohorts=dict(args.cohorts),
            output_directory=args.output,
            overwrite=args.overwrite,
            generation_command=command,
        )
    except _KNOWN_ERRORS as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(f"robustness comparison written to {result.output_directory}")
    print(f"decision: {result.decision}")
    print(
        "high-noise balanced-accuracy gain: "
        f"{result.high_noise_balanced_accuracy_gain:.4f}"
    )
    print(
        "combined-OOD balanced-accuracy gain: "
        f"{result.combined_ood_balanced_accuracy_gain:.4f}"
    )
    print(f"pilot balanced-accuracy drop: {result.pilot_balanced_accuracy_drop:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
