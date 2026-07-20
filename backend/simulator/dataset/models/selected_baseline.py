"""The PR168-selected baseline configuration, frozen (PR169/PR170 spec
section 1: "preserve the base model" / "use the selected PR168 pipeline
exactly").

Single canonical source for every downstream decision-layer package
(`calibration`, `alert_policy`, and any future one) that must reuse
PR168's *result* — logistic regression, feature set D, `C=0.01` — without
re-running `models.search`'s selection. Deliberately separate from
`models/config.py`, which defines the *search space* PR168 explored, not
its outcome: hardcoding the outcome there would misleadingly suggest it's
part of the search policy rather than a frozen, already-decided choice.
"""

from __future__ import annotations

BASE_MODEL_TYPE = "logistic_regression"
BASE_FEATURE_GROUP = "D"
BASE_LOGISTIC_REGRESSION_C = 0.01
