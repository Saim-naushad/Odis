"""Small, explicit hyperparameter search over the validation split (PR168
spec section 6).

Every trial this module runs is returned in the result list — nothing is
discarded — so `experiment.py` can report "every attempted configuration"
verbatim. Selection always maximizes validation balanced accuracy; test
data is never touched here.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass
from typing import Any

import numpy as np
from sklearn.metrics import balanced_accuracy_score
from sklearn.pipeline import Pipeline

from backend.simulator.dataset.models.config import (
    HGB_HYPERPARAMETER_GRID,
    LOGISTIC_REGRESSION_C_GRID,
)
from backend.simulator.dataset.models.pipelines import (
    build_histogram_gb_pipeline,
    build_logistic_regression_pipeline,
    fit_histogram_gb,
)

LOGISTIC_REGRESSION = "logistic_regression"
HISTOGRAM_GRADIENT_BOOSTING = "histogram_gradient_boosting"


@dataclass(frozen=True)
class SearchTrial:
    model_type: str
    feature_group: str
    hyperparameters: dict[str, Any]
    validation_balanced_accuracy: float

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "model_type": self.model_type,
            "feature_group": self.feature_group,
            "hyperparameters": self.hyperparameters,
            "validation_balanced_accuracy": self.validation_balanced_accuracy,
        }


def _fit_and_score(
    pipeline: Pipeline,
    x_train: np.ndarray,
    y_train: np.ndarray,
    x_val: np.ndarray,
    y_val: np.ndarray,
    *,
    is_hgb: bool,
) -> float:
    if is_hgb:
        fit_histogram_gb(pipeline, x_train, y_train)
    else:
        pipeline.fit(x_train, y_train)
    predictions = pipeline.predict(x_val)
    with warnings.catch_warnings():
        # A small hyperparameter search trial can predict zero rows of a
        # rare class on a given fold — a scoring artifact of that trial,
        # not a data or pipeline defect, and expected to happen a handful
        # of times across a 32-trial grid.
        warnings.filterwarnings(
            "ignore",
            message="y_pred contains classes not in y_true",
            category=UserWarning,
        )
        return float(balanced_accuracy_score(y_val, predictions))


def search_logistic_regression(
    x_train: np.ndarray,
    y_train: np.ndarray,
    x_val: np.ndarray,
    y_val: np.ndarray,
    feature_group: str,
) -> list[SearchTrial]:
    trials = []
    for c in LOGISTIC_REGRESSION_C_GRID:
        pipeline = build_logistic_regression_pipeline(c)
        accuracy = _fit_and_score(
            pipeline, x_train, y_train, x_val, y_val, is_hgb=False
        )
        trials.append(
            SearchTrial(LOGISTIC_REGRESSION, feature_group, {"C": c}, accuracy)
        )
    return trials


def search_histogram_gb(
    x_train: np.ndarray,
    y_train: np.ndarray,
    x_val: np.ndarray,
    y_val: np.ndarray,
    feature_group: str,
) -> list[SearchTrial]:
    trials = []
    for hyperparameters in HGB_HYPERPARAMETER_GRID:
        pipeline = build_histogram_gb_pipeline(**hyperparameters)
        accuracy = _fit_and_score(
            pipeline, x_train, y_train, x_val, y_val, is_hgb=True
        )
        trials.append(
            SearchTrial(
                HISTOGRAM_GRADIENT_BOOSTING,
                feature_group,
                dict(hyperparameters),
                accuracy,
            )
        )
    return trials


def best_trial(trials: list[SearchTrial]) -> SearchTrial:
    return max(trials, key=lambda t: t.validation_balanced_accuracy)


def build_pipeline_for_trial(trial: SearchTrial) -> Pipeline:
    if trial.model_type == LOGISTIC_REGRESSION:
        return build_logistic_regression_pipeline(trial.hyperparameters["C"])
    if trial.model_type == HISTOGRAM_GRADIENT_BOOSTING:
        return build_histogram_gb_pipeline(**trial.hyperparameters)
    raise ValueError(f"unknown model_type: {trial.model_type!r}")


def fit_trial_pipeline(
    trial: SearchTrial, pipeline: Pipeline, x_train: np.ndarray, y_train: np.ndarray
) -> Pipeline:
    if trial.model_type == HISTOGRAM_GRADIENT_BOOSTING:
        return fit_histogram_gb(pipeline, x_train, y_train)
    pipeline.fit(x_train, y_train)
    return pipeline
