"""scikit-learn pipelines for the two required baselines (PR168 spec
sections 1 and 5).

Both bundle preprocessing and estimator in a single `Pipeline` (spec
section 5: "keep preprocessing and estimator bundled in one serializable
scikit-learn pipeline") so `joblib.dump`/`load` round-trips the whole
thing, and so no preprocessing statistic can ever be fit outside of
`Pipeline.fit`'s own train-only call in `experiment.py`.

No `SimpleImputer` in either pipeline: `data.load_experiment_dataset`
already raises on any non-finite value, so an imputer would have nothing
to do — spec section 5 explicitly warns against adding one "merely by
habit".
"""

from __future__ import annotations

import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.utils.class_weight import compute_sample_weight

from backend.simulator.dataset.models.config import (
    LOGISTIC_REGRESSION_MAX_ITER,
    RANDOM_SEED,
)

CLASSIFIER_STEP_NAME = "classifier"


def build_logistic_regression_pipeline(c: float) -> Pipeline:
    """Training-split-only-fitted `StandardScaler` + multinomial logistic
    regression, `class_weight="balanced"` per spec section 4."""
    return Pipeline(
        [
            ("scaler", StandardScaler()),
            (
                CLASSIFIER_STEP_NAME,
                LogisticRegression(
                    C=c,
                    class_weight="balanced",
                    max_iter=LOGISTIC_REGRESSION_MAX_ITER,
                    random_state=RANDOM_SEED,
                    solver="lbfgs",
                ),
            ),
        ]
    )


def build_histogram_gb_pipeline(
    *,
    learning_rate: float,
    max_leaf_nodes: int,
    min_samples_leaf: int,
    l2_regularization: float,
) -> Pipeline:
    """No standardization (tree-based, scale-invariant splits) — spec
    section 5: "do not standardize unless technically necessary"."""
    return Pipeline(
        [
            (
                CLASSIFIER_STEP_NAME,
                HistGradientBoostingClassifier(
                    learning_rate=learning_rate,
                    max_leaf_nodes=max_leaf_nodes,
                    min_samples_leaf=min_samples_leaf,
                    l2_regularization=l2_regularization,
                    random_state=RANDOM_SEED,
                ),
            ),
        ]
    )


def balanced_sample_weight(y_train: np.ndarray) -> np.ndarray:
    """Documented sample weights derived exclusively from training labels
    (spec section 4: histogram gradient boosting has no `class_weight`
    constructor argument, so `HistGradientBoostingClassifier.fit`'s
    `sample_weight` is the supported substitute)."""
    return np.asarray(compute_sample_weight("balanced", y_train))


def fit_histogram_gb(
    pipeline: Pipeline, x_train: np.ndarray, y_train: np.ndarray
) -> Pipeline:
    weights = balanced_sample_weight(y_train)
    fit_params = {f"{CLASSIFIER_STEP_NAME}__sample_weight": weights}
    pipeline.fit(x_train, y_train, **fit_params)
    return pipeline
