"""CLI entry point: `python -m backend.simulator.inference.bundle_cli`.

The one deterministic local packaging command (spec section 2): copies
and re-verifies PR175's promoted artifacts into the runtime bundle
directory `bundle.package_promoted_artifact` defines.

::

    python -m backend.simulator.inference.bundle_cli \\
        --source datasets/pem-faults-robust-training-v1-policy/artifacts \\
        --output artifacts/models/plant_alpha_fault_v1 \\
        --training-dataset-id pem-faults-robust-training-v1
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from backend.simulator.inference.bundle import (
    DEFAULT_SYSTEM_VERSION,
    BundleOutputExistsError,
    SourceArtifactMismatchError,
    SourceArtifactNotFoundError,
    package_promoted_artifact,
)

_KNOWN_ERRORS = (
    SourceArtifactNotFoundError,
    SourceArtifactMismatchError,
    BundleOutputExistsError,
)


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--training-dataset-id", required=True)
    parser.add_argument("--system-version", default=DEFAULT_SYSTEM_VERSION)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        paths = package_promoted_artifact(
            args.source,
            args.output,
            training_dataset_id=args.training_dataset_id,
            system_version=args.system_version,
            overwrite=args.overwrite,
        )
    except _KNOWN_ERRORS as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(f"packaged runtime bundle to {args.output}")
    print(f"  pipeline: {paths.pipeline_path}")
    print(f"  alert policy: {paths.alert_policy_path}")
    print(f"  metadata: {paths.metadata_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
