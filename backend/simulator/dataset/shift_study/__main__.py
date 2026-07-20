"""CLI entry point: `python -m backend.simulator.dataset.shift_study`.

::

    python -m backend.simulator.dataset.shift_study \\
        --combined-ood-evaluation datasets/pem-faults-ood-v1-evaluation \\
        --cohort high_load=datasets/pem-faults-shift-high-load-evaluation \\
        --cohort hot_start=datasets/pem-faults-shift-hot-start-evaluation \\
        --cohort late_onset=datasets/pem-faults-shift-late-onset-evaluation \\
        --cohort high_noise=datasets/pem-faults-shift-high-noise-evaluation \\
        --audit high_load=datasets/pem-faults-shift-high-load-audit \\
        --audit hot_start=datasets/pem-faults-shift-hot-start-audit \\
        --audit late_onset=datasets/pem-faults-shift-late-onset-audit \\
        --audit high_noise=datasets/pem-faults-shift-high-noise-audit \\
        --output datasets/pem-faults-shift-study

Each `--cohort`/`--audit` value is `NAME=PATH`. `--audit` is optional per
cohort (the "Physical audit" report section is simply omitted for a
cohort with no `--audit` entry). There is no separate `--id-evaluation`
flag: every PR171 evaluation output already embeds the identical pilot
test-split ("ID") metrics it was itself scored against, so nothing
further needs to be supplied — see `docs/isolated-shift-evaluation.md`.
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
from backend.simulator.dataset.shift_study.cohort_loading import (
    ArtifactHashMismatchError,
    DuplicateCohortNameError,
    MissingCohortFileError,
)
from backend.simulator.dataset.shift_study.generate import (
    ShiftStudyOutputExistsError,
    run_shift_study,
)


def _parse_named_path(value: str) -> tuple[str, Path]:
    if "=" not in value:
        raise argparse.ArgumentTypeError(
            f"expected NAME=PATH, got {value!r}"
        )
    name, _, path = value.partition("=")
    if not name or not path:
        raise argparse.ArgumentTypeError(
            f"expected NAME=PATH with both non-empty, got {value!r}"
        )
    return name, Path(path)


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--combined-ood-evaluation", type=Path, default=None)
    parser.add_argument(
        "--cohort",
        dest="cohorts",
        action="append",
        type=_parse_named_path,
        default=[],
        help="NAME=PATH to an isolated-shift PR171 evaluation output directory; "
        "repeatable, at least one required.",
    )
    parser.add_argument(
        "--audit",
        dest="audits",
        action="append",
        type=_parse_named_path,
        default=[],
        help="NAME=PATH to a cohort's PR166 audit output directory; optional, "
        "repeatable.",
    )
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(argv)
    if not args.cohorts:
        parser.error("at least one --cohort NAME=PATH is required")
    return args


_KNOWN_ERRORS = (
    ShiftStudyOutputExistsError,
    MissingCohortFileError,
    DuplicateCohortNameError,
    ArtifactHashMismatchError,
    ManifestHashMismatchError,
    FeatureColumnOrderError,
    RowAlignmentError,
    SplitOverlapError,
    SourceDatasetNotFoundError,
    NonFiniteFeatureValueError,
)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    command = "python -m backend.simulator.dataset.shift_study " + " ".join(
        sys.argv[1:] if argv is None else argv
    )

    try:
        result = run_shift_study(
            combined_ood_evaluation=args.combined_ood_evaluation,
            cohort_evaluations=args.cohorts,
            cohort_audits=args.audits,
            output_directory=args.output,
            overwrite=args.overwrite,
            generation_command=command,
        )
    except _KNOWN_ERRORS as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(f"shift study written to {result.output_directory}")
    print(f"primary generalization failure: {result.primary_failure}")
    print(f"recommended next direction: {result.recommendation}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
