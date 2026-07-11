"""Legacy explainable decision entry point.

Canonical reasoning lives under ``src/application/reasoning/``. This module
re-exports the backend compatibility adapter so existing imports remain stable.
"""

from __future__ import annotations

from backend.app.application.reasoning_compatibility import (
    ExplainableDecision,
    build_explainable_decision,
)

__all__ = ["ExplainableDecision", "build_explainable_decision"]
