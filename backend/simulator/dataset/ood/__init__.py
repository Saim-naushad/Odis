"""PR171 out-of-distribution (OOD) evaluation of the frozen PR168 model and
PR170 alert policy.

This package never fits, refits, calibrates, or reselects anything — every
learned artifact it touches (the PR168 `selected_pipeline.joblib` and the
PR170 `alert_policy.json` state-machine config) is loaded and used exactly
as already selected. See `docs/out-of-distribution-evaluation.md` for the
full rationale and `artifacts.load_frozen_artifacts` for the compatibility
checks that make "silently retrain as a fallback" impossible.
"""

from __future__ import annotations
