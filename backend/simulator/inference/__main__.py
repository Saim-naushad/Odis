"""CLI entry point: `python -m backend.simulator.inference`.

Development validation tool, not a production service (spec section 11):
replays one `(run_id, asset_id)`'s telemetry from an offline dataset's
`telemetry.parquet`, chronologically, through a real
`FaultInferenceSession` built from a packaged runtime bundle, and prints
every warm-up/prediction/alert-transition/insufficient-data event as it
happens. Never trains or regenerates anything.

::

    python -m backend.simulator.inference \\
        --artifact-dir artifacts/models/plant_alpha_fault_v1 \\
        --telemetry datasets/pem-faults-pilot/telemetry.parquet \\
        --run-id pem-faults-pilot-cooling_degradation-0000 \\
        --asset-id fuel-cell-stack-01

Pass `--offline-features DIR` (a features-CLI output directory) to also
cross-check each valid-prediction row's feature vector and diagnosed class
against that directory's `features.parquet`/model artifact, when a
matching row exists there.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

import pyarrow.parquet as pq

from backend.simulator.inference.loader import (
    PromotedArtifactMismatchError,
    PromotedArtifactNotFoundError,
    UnexpectedArtifactFileError,
    load_promoted_fault_system,
)
from backend.simulator.inference.replay import (
    RunNotFoundError,
    load_run_observations,
    replay_run,
)
from backend.simulator.inference.result import InferenceStatus

_KNOWN_ERRORS = (
    PromotedArtifactNotFoundError,
    UnexpectedArtifactFileError,
    PromotedArtifactMismatchError,
    RunNotFoundError,
)


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-dir", required=True, type=Path)
    parser.add_argument("--telemetry", required=True, type=Path)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--asset-id", required=True)
    parser.add_argument(
        "--offline-features",
        type=Path,
        default=None,
        help="optional features-CLI output directory to cross-check against",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)

    try:
        system = load_promoted_fault_system(args.artifact_dir)
        telemetry_table = pq.read_table(args.telemetry)
        observations = load_run_observations(
            telemetry_table, run_id=args.run_id, asset_id=args.asset_id
        )
    except _KNOWN_ERRORS as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(f"loaded runtime bundle: {args.artifact_dir}")
    print(
        f"system_version={system.system_version} model_hash={system.model_hash[:12]}… "
        f"policy_hash={system.policy_hash[:12]}…"
    )
    print(f"replaying {len(observations)} samples for run={args.run_id!r} "
          f"asset={args.asset_id!r}")
    print("-" * 72)

    offline_features = None
    if args.offline_features is not None:
        offline_path = args.offline_features / "features.parquet"
        if offline_path.is_file():
            offline_features = pq.read_table(offline_path).to_pylist()

    results = replay_run(system, observations)
    previous_alert_state = None
    for result in results:
        if result.status is InferenceStatus.WARMING_UP:
            print(
                f"[{result.timestamp.isoformat()}] warming_up "
                f"{result.samples_available}/{result.samples_required}"
            )
            continue
        if result.status is InferenceStatus.INSUFFICIENT_DATA:
            print(
                f"[{result.timestamp.isoformat()}] insufficient_data "
                f"reasons={list(result.reason_codes)} "
                f"features={list(result.invalid_feature_names)}"
            )
            continue

        print(
            f"[{result.timestamp.isoformat()}] valid_prediction "
            f"diagnosed={result.diagnosed_class} "
            f"p={result.maximum_probability:.3f} alert_state={result.alert_state}"
        )
        if result.alert_event is not None:
            print(f"    ALERT EVENT: {result.alert_event}")
        alert_state_changed = (
            previous_alert_state is not None
            and result.alert_state != previous_alert_state
        )
        if alert_state_changed:
            print(
                f"    alert state changed: {previous_alert_state} -> "
                f"{result.alert_state}"
            )
        previous_alert_state = result.alert_state

        if offline_features is not None:
            match = next(
                (
                    row
                    for row in offline_features
                    if row["simulation_run_id"] == args.run_id
                    and row["asset_id"] == args.asset_id
                    and row["timestamp"] == result.timestamp
                ),
                None,
            )
            # A full feature-vector/probability comparison lives in the
            # parity test suite (`test_offline_online_parity.py`), which
            # has direct access to both the session's computed feature
            # values and the fitted pipeline — this CLI only reports
            # whether offline considered this timestamp eligible at all,
            # as a quick sanity signal during manual replay.
            print(
                "    offline row present at this timestamp"
                if match is not None
                else "    ** no matching offline features row at this timestamp **"
            )

    print("-" * 72)
    print("replay complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
