"""Lightweight checks for the demo validation shell script."""

from __future__ import annotations

import json
import os
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "validate_demo_environment.sh"


def test_validate_demo_environment_script_has_valid_bash_syntax() -> None:
    subprocess.run(["bash", "-n", str(SCRIPT)], check=True)


def test_py_asset_ids_helper_under_set_u() -> None:
    result = subprocess.run(
        [
            "bash",
            "-c",
            (
                "set -euo pipefail; "
                f"source {SCRIPT}; "
                'ASSETS_JSON=\'[{"id":"fuel-cell-stack-01"}]\'; '
                'py_asset_ids "${ASSETS_JSON}"'
            ),
        ],
        text=True,
        capture_output=True,
        check=True,
    )
    assert result.stdout.strip() == "fuel-cell-stack-01"


def test_py_observation_count_helper() -> None:
    observations = [{"id": "a"}, {"id": "b"}]

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            assert self.path == "/observations"
            body = json.dumps(observations).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            return

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        port = server.server_address[1]
        env = os.environ.copy()
        env["SIMULATOR_API_BASE_URL"] = f"http://127.0.0.1:{port}"
        result = subprocess.run(
            [
                "bash",
                "-c",
                (
                    "set -euo pipefail; "
                    f"source {SCRIPT}; "
                    "py_observation_count"
                ),
            ],
            text=True,
            capture_output=True,
            check=True,
            env=env,
        )
        assert result.stdout.strip() == "2"
    finally:
        server.shutdown()
