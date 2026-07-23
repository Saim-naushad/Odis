"""Ephemeral Docker Compose lifecycle for one benchmark run (PR181).

A fresh, uniquely-named Compose project + volumes per repetition is the
default isolation mechanism (preferred over reusing a stack across
repetitions, per the run-isolation correction): it structurally rules out
cross-repetition contamination (accumulated observations, lingering open
investigations, retained Kafka messages/offsets, carried-over Prometheus
counters, accumulated outbox/timeline rows) rather than relying on
run-scoped queries to filter it out after the fact.

Every host port the benchmark needs is resolved up front and pre-flight
checked as free *before* any container is created — never a partial start
followed by a failure. Teardown only ever targets the exact project name
this instance created; it never runs a broad Docker cleanup command.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import time
from dataclasses import dataclass

from scripts.benchmark_odis.config import RunConfig

COMPOSE_FILES: tuple[str, ...] = ("docker-compose.yml", "docker-compose.benchmark.yml")

# Offset from the standard dev-overlay ports (docker-compose.dev.yml) so a
# benchmark run can coexist with an already-running normal dev/demo stack.
DEFAULT_PORTS: dict[str, int] = {
    "api": 18000,
    "postgres": 15432,
    "kafka": 19092,
    "redis": 16379,
    "prometheus": 19090,
}

# Services started for every benchmark run — deliberately excludes the
# `demo` profile's `demo-plant` container: the benchmark drives its own
# simulator subprocess on the host instead (`simulator_driver.py`), so
# asset count/scenario/cadence can vary per run without rebuilding a
# container.
SERVICES: tuple[str, ...] = (
    "postgres",
    "redis",
    "kafka",
    "api",
    "worker",
    "reasoning-bridge-worker",
    "fault-inference-worker",
    "prometheus",
)


class StackError(RuntimeError):
    """Raised when the benchmark stack cannot be started or reached."""


@dataclass(frozen=True)
class StackEndpoints:
    api_base_url: str
    database_url: str
    kafka_bootstrap_servers: str
    redis_url: str
    prometheus_base_url: str


def resolve_ports(*, port_offset: int = 0) -> dict[str, int]:
    """Every port this run will claim. `port_offset` lets repeated
    repetitions run concurrently in the future; the default (0) always
    resolves to `DEFAULT_PORTS`."""
    return {name: port + port_offset for name, port in DEFAULT_PORTS.items()}


def _port_is_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.5)
        try:
            probe.bind(("127.0.0.1", port))
        except OSError:
            return False
        return True


def preflight_check_ports(ports: dict[str, int]) -> None:
    """Fail before creating anything if any resolved port is already bound."""
    busy = {name: port for name, port in ports.items() if not _port_is_free(port)}
    if busy:
        details = ", ".join(f"{name}={port}" for name, port in sorted(busy.items()))
        raise StackError(
            "benchmark cannot start: the following host ports are already in "
            f"use: {details}. Stop whatever is using them (an existing dev/demo "
            "stack?) or free them before retrying — the benchmark never "
            "partially starts a stack."
        )


def endpoints_for(ports: dict[str, int]) -> StackEndpoints:
    return StackEndpoints(
        api_base_url=f"http://localhost:{ports['api']}",
        database_url=(
            f"postgresql+psycopg://odis:odis@localhost:{ports['postgres']}/odis"
        ),
        kafka_bootstrap_servers=f"localhost:{ports['kafka']}",
        redis_url=f"redis://localhost:{ports['redis']}/0",
        prometheus_base_url=f"http://localhost:{ports['prometheus']}",
    )


def _compose_args(project_name: str) -> list[str]:
    args = ["docker", "compose", "-p", project_name]
    for compose_file in COMPOSE_FILES:
        args += ["-f", compose_file]
    return args


class BenchmarkStack:
    """Owns exactly one Compose project's lifecycle. Never touches any
    project other than the one it created."""

    def __init__(self, config: RunConfig, *, port_offset: int = 0) -> None:
        self._project_name = config.compose_project_name()
        self._ports = resolve_ports(port_offset=port_offset)
        self.endpoints = endpoints_for(self._ports)
        self._env = {
            "API_PORT": str(self._ports["api"]),
            "BENCHMARK_POSTGRES_PORT": str(self._ports["postgres"]),
            "BENCHMARK_KAFKA_PORT": str(self._ports["kafka"]),
            "BENCHMARK_REDIS_PORT": str(self._ports["redis"]),
            "BENCHMARK_PROMETHEUS_PORT": str(self._ports["prometheus"]),
        }

    def up(
        self,
        *,
        up_timeout_seconds: float = 600.0,
        healthy_timeout_seconds: float = 300.0,
    ) -> None:
        """No `--build`: the built services' images are pinned to stable
        tags in `docker-compose.benchmark.yml` (`odis-api` etc, matching
        what a plain `docker compose build` under the default `odis`
        project already produces), so every repetition reuses one image
        instead of rebuilding under a fresh per-run-id project tag — the
        first run still builds-and-tags them if missing (Compose's implicit
        build-if-image-absent behavior), every run after that is a plain
        container start. `up_timeout_seconds` is generous specifically to
        cover that first-ever build.
        """
        preflight_check_ports(self._ports)
        env = {**os.environ, **self._env}
        result = subprocess.run(
            [*_compose_args(self._project_name), "up", "-d", *SERVICES],
            env=env,
            capture_output=True,
            text=True,
            timeout=up_timeout_seconds,
        )
        if result.returncode != 0:
            # `up -d` failed outright — nothing (or a partial set) may have
            # been created; tear down this exact project before surfacing
            # the error so a failed attempt never leaks containers.
            self.down()
            raise StackError(
                f"docker compose up failed for project {self._project_name!r}: "
                f"{result.stderr.strip()}"
            )
        self._wait_healthy(timeout_seconds=healthy_timeout_seconds)

    def _wait_healthy(self, *, timeout_seconds: float) -> None:
        env = {**os.environ, **self._env}
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            result = subprocess.run(
                [*_compose_args(self._project_name), "ps", "--format", "json"],
                env=env,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0 and result.stdout.strip():
                statuses = []
                for line in result.stdout.strip().splitlines():
                    try:
                        statuses.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
                if statuses and all(
                    "healthy" in entry.get("Health", "healthy")
                    or entry.get("Health", "") == ""
                    for entry in statuses
                ):
                    return
            time.sleep(2.0)
        self.down()
        raise StackError(
            f"benchmark stack {self._project_name!r} did not become healthy "
            f"within {timeout_seconds}s"
        )

    def down(self, *, remove_volumes: bool = True) -> None:
        env = {**os.environ, **self._env}
        args = [*_compose_args(self._project_name), "down"]
        if remove_volumes:
            args.append("-v")
        subprocess.run(args, env=env, capture_output=True, text=True, timeout=120)
