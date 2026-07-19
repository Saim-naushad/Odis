"""Leakage-safe baseline fault-diagnosis experiments (PR168).

Trains and evaluates exactly two supervised classifiers (logistic
regression, histogram gradient boosting) over four progressively richer
feature-set ablations (A: raw, B: +temporal, C: +cross-signal, D: +physics
residuals) against the PR167 feature dataset, using the validation split
for model/hyperparameter selection and the test split exactly once, at the
end, for a final honest read.

Entry point: `python -m backend.simulator.dataset.models`.
"""

from __future__ import annotations
