"""Helpers for identifying worker processes."""

from __future__ import annotations

import os
import socket


def build_worker_id() -> str:
    """Return a stable identifier for the current worker process."""
    hostname = socket.gethostname()
    return f"{hostname}-{os.getpid()}"
