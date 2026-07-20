"""Uncalibrated temporal alert-state policy (PR170).

Wraps the PR168-selected logistic-regression pipeline's native (never
calibrated) probabilities in a deterministic hysteresis state machine —
healthy / pending_<class> / confirmed_<class> — to reduce operator-facing
false alerts through temporal confirmation and exit hysteresis, without
changing any row-level class prediction. The PR169 calibrated policy
remains a separate, historical, non-superseding comparison point.

Entry point: `python -m backend.simulator.dataset.alert_policy`.
"""

from __future__ import annotations
