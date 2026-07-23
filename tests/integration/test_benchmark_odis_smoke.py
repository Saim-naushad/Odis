"""Real-stack smoke test for scripts.benchmark_odis (PR181).

Exercises the actual orchestration path — ephemeral Compose stack, host
simulator subprocess, live Kafka/SSE/API observers, Postgres reconciliation
— against a real (if minimal) benchmark run. Slow (spins up a full Compose
project) and Docker-dependent, so it's gated behind the `benchmark` marker,
separate from `integration`, and skipped unless Docker is actually
reachable. Not part of the default `pytest -m "not integration"` run.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from scripts.benchmark_odis.__main__ import main

# Also marked `integration` (not just `benchmark`) so the existing
# `pytest -m "not integration"` convention this repo already uses for every
# other docker-dependent test excludes these too, without requiring a
# separate exclusion flag to be remembered. `benchmark` exists in addition
# so these particularly slow full-stack runs can be selected/excluded on
# their own (`-m "integration and not benchmark"` still runs ordinary
# integration tests without spinning up a benchmark stack).
pytestmark = [pytest.mark.integration, pytest.mark.benchmark]


def _docker_available_or_skip() -> None:
    if shutil.which("docker") is None:
        pytest.skip("docker is not installed")
    try:
        result = subprocess.run(
            ["docker", "info"], capture_output=True, timeout=10
        )
    except (OSError, subprocess.TimeoutExpired):
        pytest.skip("docker is not reachable")
    if result.returncode != 0:
        pytest.skip("docker daemon is not running")


def test_performance_mode_smoke_run_writes_artifacts(tmp_path: Path) -> None:
    _docker_available_or_skip()
    exit_code = main(
        [
            "--assets",
            "1",
            "--scenario",
            "normal_operation",
            "--duration",
            "60",
            "--publish-interval",
            "1.1",
            "--output-dir",
            str(tmp_path),
        ]
    )
    assert exit_code == 0
    run_dirs = list(tmp_path.iterdir())
    assert len(run_dirs) == 1
    run_dir = run_dirs[0]
    assert (run_dir / "summary.json").exists()
    assert (run_dir / "environment.json").exists()
    assert (run_dir / "report.md").exists()
