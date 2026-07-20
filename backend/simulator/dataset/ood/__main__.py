"""CLI entry point: `python -m backend.simulator.dataset.ood`.

::

    python -m backend.simulator.dataset.ood \\
        --training-features datasets/pem-faults-pilot-features \\
        --ood-features datasets/pem-faults-ood-v1-features \\
        --models datasets/pem-faults-pilot-models \\
        --alert-policy datasets/pem-faults-pilot-alert-policy \\
        --output datasets/pem-faults-ood-v1-evaluation
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
from backend.simulator.dataset.ood.artifacts import (
    ArtifactNotFoundError,
    IncompatibleArtifactError,
)
from backend.simulator.dataset.ood.generate import (
    OodOutputExistsError,
    run_ood_evaluation,
)


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--training-features", required=True, type=Path)
    parser.add_argument("--ood-features", required=True, type=Path)
    parser.add_argument("--models", required=True, type=Path)
    parser.add_argument("--alert-policy", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--training-dataset",
        type=Path,
        default=None,
        help="Source pilot dataset directory; defaults to the training "
        "feature manifest's recorded source_dataset.directory.",
    )
    parser.add_argument(
        "--ood-dataset",
        type=Path,
        default=None,
        help="Source OOD dataset directory; defaults to the OOD feature "
        "manifest's recorded source_dataset.directory.",
    )
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args(argv)


_KNOWN_ERRORS = (
    ArtifactNotFoundError,
    IncompatibleArtifactError,
    OodOutputExistsError,
    ManifestHashMismatchError,
    FeatureColumnOrderError,
    RowAlignmentError,
    SplitOverlapError,
    SourceDatasetNotFoundError,
    NonFiniteFeatureValueError,
)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    command = "python -m backend.simulator.dataset.ood " + " ".join(
        sys.argv[1:] if argv is None else argv
    )

    try:
        result = run_ood_evaluation(
            training_features_dir=args.training_features,
            ood_features_dir=args.ood_features,
            models_dir=args.models,
            alert_policy_dir=args.alert_policy,
            output_directory=args.output,
            training_dataset_dir=args.training_dataset,
            ood_dataset_dir=args.ood_dataset,
            overwrite=args.overwrite,
            generation_command=command,
        )
    except _KNOWN_ERRORS as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(f"OOD evaluation written to {result.output_directory}")
    print(f"verdict: {result.verdict}")
    print(f"OOD balanced accuracy: {result.ood_balanced_accuracy:.3f}")
    print(
        "OOD false alert events/healthy-hour: "
        f"{result.ood_false_alert_events_per_healthy_hour:.3f}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
