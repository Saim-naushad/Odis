"""Host-side simulator subprocess driver (PR181).

Launches `python -m backend.simulator` as a plain host subprocess against a
benchmark stack's host-exposed Kafka/API endpoints, with env-var overrides
for asset count/scenario/cadence — no simulator code changes. Kept on the
host (rather than in a container) so asset count and scenario can vary per
repetition without a container rebuild.
"""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import UTC, datetime

from scripts.benchmark_odis.config import RunConfig
from scripts.benchmark_odis.stack import StackEndpoints


class SimulatorProcess:
    """One `backend.simulator` subprocess for the duration of a run."""

    def __init__(
        self, config: RunConfig, endpoints: StackEndpoints, *, run_id: str
    ) -> None:
        self._config = config
        self._endpoints = endpoints
        self._run_id = run_id
        self._process: subprocess.Popen[bytes] | None = None
        self.launched_at: datetime | None = None

    def _env(self) -> dict[str, str]:
        return {
            **os.environ,
            "SIMULATOR_TRANSPORT": self._config.transport,
            "SIMULATOR_SCENARIO": self._config.scenario,
            "SIMULATOR_RUN_ID": self._run_id,
            "SIMULATOR_ASSET_IDS": ",".join(self._config.asset_ids()),
            "SIMULATOR_API_BASE_URL": self._endpoints.api_base_url,
            "SIMULATOR_KAFKA_BOOTSTRAP_SERVERS": (
                self._endpoints.kafka_bootstrap_servers
            ),
            "SIMULATOR_KAFKA_SAMPLE_INTERVAL_SECONDS": str(
                self._config.kafka_sample_interval_seconds
            ),
            "SIMULATOR_KAFKA_PUBLISH_INTERVAL_SECONDS": str(
                self._config.kafka_publish_interval_seconds
            ),
        }

    def start(self) -> None:
        self.launched_at = datetime.now(UTC)
        self._process = subprocess.Popen(
            [sys.executable, "-m", "backend.simulator"],
            env=self._env(),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )

    def stop(self, *, timeout_seconds: float = 10.0) -> None:
        if self._process is None:
            return
        self._process.terminate()
        try:
            self._process.wait(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            self._process.kill()
            self._process.wait(timeout=timeout_seconds)

    def is_running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def __enter__(self) -> SimulatorProcess:
        self.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self.stop()
