"""CLI entry point: `python -m backend.simulator.dataset.features`.

::

    python -m backend.simulator.dataset.features \\
        --dataset datasets/pem-faults-pilot \\
        --output datasets/pem-faults-pilot-features
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from backend.simulator.dataset.audit.loader import DatasetNotFoundError
from backend.simulator.dataset.features.generate import (
    FeatureOutputExistsError,
    generate_features,
)


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    command = "python -m backend.simulator.dataset.features " + " ".join(
        sys.argv[1:] if argv is None else argv
    )

    try:
        result = generate_features(
            args.dataset,
            args.output,
            overwrite=args.overwrite,
            generation_command=command,
        )
    except (DatasetNotFoundError, FeatureOutputExistsError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(f"features written to {result.output_directory}")
    print(
        f"feature_count={result.feature_count} "
        f"eligible_rows={result.eligible_rows} "
        f"dropped_warmup_rows={result.dropped_warmup_rows}"
    )
    print(
        f"valid_rows={result.valid_rows} rejected_rows={result.rejected_rows} "
        f"rejection_rate={result.rejected_rows / result.eligible_rows:.4%}"
        if result.eligible_rows > 0
        else "valid_rows=0 rejected_rows=0 rejection_rate=0.0000%"
    )
    print(f"split_counts={result.split_counts}")
    print(f"class_distribution={result.class_distribution}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
