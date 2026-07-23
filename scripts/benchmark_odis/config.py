"""Benchmark run configuration, validation, and environment capture (PR181).

`RunConfig` is the single source of truth for one benchmark invocation;
`capture_environment` records everything task section 3 requires (git
commit, OS/CPU/memory, Docker/Python/Node versions, model system
version/hash, cadence, asset count, scenario, seed, run duration, timestamp)
so a `report.md` can never be read without knowing exactly what produced it.
"""

from __future__ import annotations

import json
import os
import platform
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

REPO_ROOT = Path(__file__).resolve().parents[2]
MODEL_BUNDLE_DIR = REPO_ROOT / "artifacts" / "models" / "plant_alpha_fault_v1"

Scenario = Literal["normal_operation", "cooling_degradation"]
Mode = Literal["performance", "reliability"]

# The 4 real Plant Alpha stacks always come first — `CoolingDegradationScenario`
# targets `fuel-cell-stack-01` by default, so it's always present regardless
# of fleet size. Additional assets are clearly bench-named, matching the
# `*bench*` convention `scripts/validate_demo_environment.sh` already checks
# for, so residue is always identifiable and cleanable.
REAL_ASSET_IDS: tuple[str, ...] = (
    "fuel-cell-stack-01",
    "fuel-cell-stack-02",
    "fuel-cell-stack-03",
    "fuel-cell-stack-04",
)

# Matches `SimulatorSettings.kafka_sample_interval_seconds`'s default — the
# promoted runtime's trained sample spacing (`_TRAINED_INFERENCE_CADENCE_SECONDS`
# in both `backend/simulator/config.py` and `backend/simulator/__main__.py`).
DEFAULT_KAFKA_SAMPLE_INTERVAL_SECONDS = 10.0
DEFAULT_DURATION_SECONDS = 300.0


class ConfigError(ValueError):
    """Raised for invalid or contradictory benchmark configuration."""


@dataclass(frozen=True)
class RunConfig:
    run_id: str
    mode: Mode
    scenario: Scenario
    asset_count: int
    duration_seconds: float
    kafka_publish_interval_seconds: float
    kafka_sample_interval_seconds: float
    transport: str
    output_dir: Path
    repetition_index: int = 0
    keep_stack: bool = False

    def asset_ids(self) -> tuple[str, ...]:
        """Real stacks first, then clearly bench-named synthetic assets.

        `PlantAlphaFleet.create()` (`backend/simulator/plant.py`) already
        falls back to a default baseline for any asset id it doesn't
        recognize, so no simulator change is needed to scale this list.
        """
        if self.asset_count <= len(REAL_ASSET_IDS):
            return REAL_ASSET_IDS[: self.asset_count]
        extra_count = self.asset_count - len(REAL_ASSET_IDS)
        extra = tuple(
            f"fuel-cell-stack-bench-{i:03d}" for i in range(1, extra_count + 1)
        )
        return REAL_ASSET_IDS + extra

    def run_dir(self) -> Path:
        return self.output_dir / self.run_id

    def compose_project_name(self) -> str:
        """Distinct per run-id — the isolation unit for the whole stack."""
        return f"odis-benchmark-{self.run_id}"


def validate_config(config: RunConfig) -> None:
    """Raise `ConfigError` with a specific, actionable message, or return."""
    if config.asset_count < 1:
        raise ConfigError(f"asset_count must be >= 1, got {config.asset_count}")
    if config.duration_seconds <= 0:
        raise ConfigError(
            f"duration_seconds must be positive, got {config.duration_seconds}"
        )
    if config.kafka_publish_interval_seconds <= 0:
        raise ConfigError(
            "kafka_publish_interval_seconds must be positive, got "
            f"{config.kafka_publish_interval_seconds}"
        )
    if config.kafka_sample_interval_seconds <= 0:
        raise ConfigError(
            "kafka_sample_interval_seconds must be positive, got "
            f"{config.kafka_sample_interval_seconds}"
        )
    if config.scenario not in ("normal_operation", "cooling_degradation"):
        raise ConfigError(f"unsupported scenario: {config.scenario!r}")
    if config.mode not in ("performance", "reliability"):
        raise ConfigError(f"unsupported mode: {config.mode!r}")
    if config.scenario == "cooling_degradation" and config.transport == "kafka":
        raise ConfigError(
            "scenario=cooling_degradation requires transport=kafka+http: "
            "reasoning-bridge corroboration reads persisted Observation rows "
            "(backend/app/application/reasoning_bridge/corroboration.py), not "
            "Kafka messages — transport=kafka alone would produce inference "
            "events with no corresponding stored observations to corroborate "
            "against. Use transport=kafka+http, or scenario=normal_operation "
            "if a Kafka-only throughput run (excluding the reasoning path) is "
            "genuinely intended."
        )


def make_run_id(
    *, scenario: str, asset_count: int, repetition_index: int, now: datetime
) -> str:
    """Pure function of its inputs — same inputs always produce the same id,
    so tests can assert determinism by injecting a fixed `now`.

    All-lowercase, digits/hyphens only: this id also becomes a Docker
    Compose project name (`RunConfig.compose_project_name`), which rejects
    uppercase characters.
    """
    stamp = now.strftime("%Y%m%d%H%M%S")
    scenario_slug = scenario.replace("_", "-")
    return f"{stamp}-{scenario_slug}-{asset_count}a-r{repetition_index}"


def _run_text(*args: str) -> str | None:
    try:
        result = subprocess.run(
            args, capture_output=True, text=True, timeout=10, check=False
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def _git_commit() -> str | None:
    return _run_text("git", "-C", str(REPO_ROOT), "rev-parse", "HEAD")


def _docker_version() -> str | None:
    return _run_text("docker", "--version")


def _node_version() -> str | None:
    return _run_text("node", "--version")


def _cpu_model() -> str | None:
    system = platform.system()
    if system == "Darwin":
        return _run_text("sysctl", "-n", "machdep.cpu.brand_string")
    if system == "Linux":
        try:
            with open("/proc/cpuinfo", encoding="utf-8") as handle:
                for line in handle:
                    if line.lower().startswith("model name"):
                        return line.split(":", 1)[1].strip()
        except OSError:
            return None
    return None


def _total_memory_bytes() -> int | None:
    system = platform.system()
    if system == "Darwin":
        raw = _run_text("sysctl", "-n", "hw.memsize")
        return int(raw) if raw and raw.isdigit() else None
    if system == "Linux":
        try:
            with open("/proc/meminfo", encoding="utf-8") as handle:
                for line in handle:
                    if line.startswith("MemTotal:"):
                        kib = int(line.split()[1])
                        return kib * 1024
        except (OSError, ValueError, IndexError):
            return None
    return None


def _model_metadata() -> dict[str, object]:
    metadata_path = MODEL_BUNDLE_DIR / "system_metadata.json"
    try:
        raw = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {
            "system_version": None,
            "model_hash": None,
            "policy_hash": None,
            "feature_schema_version": None,
        }
    return {
        "system_version": raw.get("system_version"),
        "model_hash": raw.get("model_hash"),
        "policy_hash": raw.get("policy_hash"),
        "feature_schema_version": raw.get("feature_schema_version"),
    }


def capture_environment(config: RunConfig) -> dict[str, object]:
    """Everything task section 3 requires an `environment.json` to record.

    `seed`/`randomness` are recorded explicitly as `null`/`"not_applicable"`
    rather than exposing a `--seed` flag: the live simulator has no RNG (its
    micro-variation is a deterministic `sin()` of tick count — seeding only
    exists in the offline dataset generator), so a seed flag would imply
    stochastic repeatability the live path doesn't have.
    """
    return {
        "git_commit": _git_commit(),
        "os": platform.system(),
        "os_release": platform.release(),
        "cpu_architecture": platform.machine(),
        "cpu_model": _cpu_model(),
        "cpu_count": os.cpu_count(),
        "memory_bytes": _total_memory_bytes(),
        "docker_version": _docker_version(),
        "python_version": platform.python_version(),
        "node_version": _node_version(),
        "model": _model_metadata(),
        "kafka_bootstrap_config": {
            "simulated_sample_interval_seconds": (
                config.kafka_sample_interval_seconds
            ),
            "wall_clock_publish_interval_seconds": (
                config.kafka_publish_interval_seconds
            ),
        },
        "asset_count": config.asset_count,
        "scenario": config.scenario,
        "mode": config.mode,
        "transport": config.transport,
        "seed": None,
        "randomness": "not_applicable",
        "run_duration_seconds": config.duration_seconds,
        "repetition_index": config.repetition_index,
        "run_id": config.run_id,
        "benchmark_timestamp": datetime.now(UTC).isoformat(),
        "host_clock_source": (
            "single host clock shared by every Docker container and the "
            "benchmark observer/poller process in this single-machine setup "
            "— no cross-host NTP skew applies"
        ),
    }
