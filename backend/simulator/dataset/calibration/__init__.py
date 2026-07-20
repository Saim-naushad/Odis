"""Calibrated confidence, abstention, and alert policy (PR169).

Wraps the PR168-selected logistic-regression pipeline (feature set D,
`C=0.01`) with sigmoid probability calibration, an explicit `"uncertain"`
abstention state, and a validation-selected consecutive-persistence alert
policy — converting raw multiclass probabilities into an operator-usable
diagnosis stream. No new model family, feature set, or dataset changes;
this is a decision layer on top of the already-selected PR168 model.

Entry point: `python -m backend.simulator.dataset.calibration`.
"""

from __future__ import annotations
