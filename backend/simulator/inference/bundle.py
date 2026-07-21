"""Runtime artifact-bundle packaging (PR176 spec section 2).

Generated files under `datasets/` are gitignored and not a reliable
deployment source (a future clone/CI checkout would have none of them).
This module defines the one deterministic, verified copy step from
PR175's promoted-system output (`datasets/pem-faults-robust-training-v1-
policy/artifacts/`) into a small, explicit runtime bundle directory —
`artifacts/models/plant_alpha_fault_v1/` by convention — containing only
`pipeline.joblib`, `alert_policy.json`, and `system_metadata.json`. No
training dataset, feature dataset, or experiment report is ever copied
here.

Repository policy check (see `docs/runtime-inference.md`): this repo has
already committed exactly one small ML artifact directly
(`backend/app/infrastructure/inference/models/persistence_drift_v1.onnx`,
439 bytes) as a deliberate carve-out from the `/datasets/` gitignore rule;
no `.joblib`/training artifact has ever been committed. The promoted
pipeline here is ~10KB — small enough to follow that same precedent — so
`artifacts/models/plant_alpha_fault_v1/` is a normal (not gitignored)
repository path. This module only ever *writes* to that path; whether to
`git add`/`git commit` the result is left to the caller.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from backend.simulator.dataset.features.config import FEATURE_SCHEMA_VERSION

DEFAULT_SYSTEM_VERSION = "plant_alpha_fault_v1"
BUNDLE_FILENAMES: tuple[str, ...] = (
    "pipeline.joblib",
    "alert_policy.json",
    "system_metadata.json",
)


class SourceArtifactNotFoundError(Exception):
    def __init__(self, path: Path) -> None:
        super().__init__(
            f"required PR175 promoted artifact not found: {path} — run the "
            "PR175 policy-selection CLI (promotion must have succeeded) "
            "before packaging a runtime bundle"
        )
        self.path = path


class SourceArtifactMismatchError(Exception):
    """Raised when the source promoted pipeline's recomputed hash does not
    match its own recorded `model_hash` — packaging never trusts an
    already-inconsistent source directory."""


class BundleOutputExistsError(Exception):
    def __init__(self, path: Path) -> None:
        super().__init__(
            f"output directory already exists and is non-empty: {path} "
            "(pass --overwrite / overwrite=True to replace it)"
        )
        self.path = path


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_json_hash(payload: dict[str, Any]) -> str:
    """`metadata_hash`'s self-referential hash: computed over every OTHER
    field, sorted-key JSON — the loader recomputes the same way to detect
    any post-packaging edit to `system_metadata.json` itself."""
    canonical = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()


@dataclass(frozen=True)
class PackagedBundlePaths:
    pipeline_path: Path
    alert_policy_path: Path
    metadata_path: Path


def package_promoted_artifact(
    source_dir: Path,
    output_dir: Path,
    *,
    training_dataset_id: str,
    system_version: str = DEFAULT_SYSTEM_VERSION,
    overwrite: bool = False,
) -> PackagedBundlePaths:
    """Copy and re-verify PR175's promoted artifacts into a runtime bundle.

    `source_dir` is a PR175 policy-selection output's `artifacts/`
    subdirectory (`promoted_pipeline.joblib`, `promoted_alert_policy.json`,
    `promoted_system_metadata.json` — only written there when PR175
    promoted). `training_dataset_id` is recorded explicitly rather than
    inferred, since the source metadata records only a content hash for
    the training dataset, not its human-readable id.
    """
    source_pipeline = source_dir / "promoted_pipeline.joblib"
    source_policy = source_dir / "promoted_alert_policy.json"
    source_metadata_path = source_dir / "promoted_system_metadata.json"
    for path in (source_pipeline, source_policy, source_metadata_path):
        if not path.is_file():
            raise SourceArtifactNotFoundError(path)

    source_metadata = json.loads(source_metadata_path.read_text())
    actual_pipeline_hash = _sha256_file(source_pipeline)
    if actual_pipeline_hash != source_metadata.get("model_hash"):
        raise SourceArtifactMismatchError(
            f"{source_pipeline}'s sha256 ({actual_pipeline_hash}) does not "
            f"match {source_metadata_path}'s recorded model_hash "
            f"({source_metadata.get('model_hash')})"
        )

    if output_dir.exists() and any(output_dir.iterdir()) and not overwrite:
        raise BundleOutputExistsError(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    pipeline_path = output_dir / "pipeline.joblib"
    alert_policy_path = output_dir / "alert_policy.json"
    metadata_path = output_dir / "system_metadata.json"

    shutil.copy2(source_pipeline, pipeline_path)
    shutil.copy2(source_policy, alert_policy_path)

    policy_hash = _sha256_file(alert_policy_path)
    safety_policy_version = source_metadata["numerical_safety_policy_version"]
    if safety_policy_version != FEATURE_SCHEMA_VERSION:
        raise SourceArtifactMismatchError(
            f"source numerical_safety_policy_version ({safety_policy_version!r}) "
            f"does not match this codebase's FEATURE_SCHEMA_VERSION "
            f"({FEATURE_SCHEMA_VERSION!r})"
        )

    payload = {
        "system_version": system_version,
        "packaged_at": datetime.now(UTC).isoformat(),
        "source_directory": str(source_dir),
        "model_hash": actual_pipeline_hash,
        "policy_hash": policy_hash,
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "safety_policy_version": safety_policy_version,
        "feature_order": source_metadata["feature_order"],
        "class_order": source_metadata["class_order"],
        "model_type": source_metadata["model_type"],
        "feature_group": source_metadata["feature_group"],
        "hyperparameters": source_metadata["hyperparameters"],
        "training_dataset_id": training_dataset_id,
        "training_dataset_manifest_sha256": (
            source_metadata["training_dataset_manifest_sha256"]
        ),
        "training_feature_manifest_sha256": (
            source_metadata["training_feature_manifest_sha256"]
        ),
        "git_commit": source_metadata.get("git_commit"),
        "promotion_decision": (
            source_metadata.get("promotion_decision", {}).get("decision")
        ),
    }
    metadata_hash = _canonical_json_hash(payload)
    payload_with_hash = {**payload, "metadata_hash": metadata_hash}
    metadata_path.write_text(json.dumps(payload_with_hash, indent=2, sort_keys=True))

    return PackagedBundlePaths(
        pipeline_path=pipeline_path,
        alert_policy_path=alert_policy_path,
        metadata_path=metadata_path,
    )
