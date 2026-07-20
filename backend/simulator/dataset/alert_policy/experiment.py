"""Top-level PR170 orchestration: uncalibrated hysteresis alert-state
policy selection, then one untouched test evaluation.

Pure computation over an already-loaded `ExperimentDataset` — no
filesystem writes here (mirrors `models/experiment.py` and `calibration/
experiment.py`'s own split). The base pipeline is fit on train exactly as
PR168 selected it (never recalibrated, never re-searched); its native
`predict_proba` drives every downstream decision. Every hysteresis
decision (entry/exit thresholds and persistence) is selected from
validation data alone; test-split rows are read exactly once, in the
final section of `run_alert_policy_experiment`.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import numpy as np

from backend.simulator.dataset.alert_policy.comparison import (
    RowSequenceFalseAlertSummary,
    compute_row_sequence_false_alerts,
    evaluate_row_sequence_detection,
    median_latency_seconds,
)
from backend.simulator.dataset.alert_policy.config import (
    BASE_FEATURE_GROUP,
    BASE_LOGISTIC_REGRESSION_C,
)
from backend.simulator.dataset.alert_policy.detection import (
    DetectionSummary,
    evaluate_detection,
)
from backend.simulator.dataset.alert_policy.event_metrics import (
    FalseAlertSummary,
    compute_false_alert_summary,
)
from backend.simulator.dataset.alert_policy.policy_search import (
    PolicySearchResult,
    search_policies,
)
from backend.simulator.dataset.alert_policy.state_machine import StateMachineConfig
from backend.simulator.dataset.models.data import ExperimentDataset
from backend.simulator.dataset.models.detection import (
    DetectionSummary as RowDetectionSummary,
)
from backend.simulator.dataset.models.metrics import (
    MulticlassMetrics,
    compute_multiclass_metrics,
)
from backend.simulator.dataset.models.pipelines import (
    build_logistic_regression_pipeline,
)
from backend.simulator.dataset.models.runtime_metrics import (
    measure_per_row_prediction_latency_ms,
)


@dataclass(frozen=True)
class RowSequenceComparisonPoint:
    """PR168's own row-sequence policy (N=3), recomputed under PR170's
    event/episode definition — never re-selected."""

    multiclass_metrics: MulticlassMetrics
    detection: RowDetectionSummary
    false_alerts: RowSequenceFalseAlertSummary

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "multiclass": self.multiclass_metrics.to_json_dict(),
            "detection": self.detection.to_json_dict(),
            "false_alerts": self.false_alerts.to_json_dict(),
            "median_correct_class_latency_seconds": (
                median_latency_seconds(self.detection)
            ),
        }


@dataclass(frozen=True)
class AlertPolicyExperimentResult:
    class_order: tuple[str, ...]
    training_seconds: float

    validation_baseline: RowSequenceComparisonPoint
    policy_search: PolicySearchResult
    selected_config: StateMachineConfig | None

    test_multiclass_metrics: MulticlassMetrics
    """Row-level, computed from the base pipeline's native predictions —
    identical to PR168's own test metrics (spec section 1)."""
    test_baseline: RowSequenceComparisonPoint
    test_detection: DetectionSummary | None
    test_false_alerts: FalseAlertSummary | None
    test_proba: np.ndarray
    """The base pipeline's native test-split probabilities — retained (not
    just summarized) so `plots.py`'s example-timeline plot can re-run the
    already-selected state machine without re-fitting anything."""

    mean_prediction_latency_ms: float
    p95_prediction_latency_ms: float

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "class_order": list(self.class_order),
            "training_seconds": self.training_seconds,
            "validation_baseline": self.validation_baseline.to_json_dict(),
            "policy_search": self.policy_search.to_json_dict(),
            "selected_config": (
                self.selected_config.to_json_dict() if self.selected_config else None
            ),
            "test_multiclass": self.test_multiclass_metrics.to_json_dict(),
            "test_baseline": self.test_baseline.to_json_dict(),
            "test_detection": (
                self.test_detection.to_json_dict() if self.test_detection else None
            ),
            "test_false_alerts": (
                self.test_false_alerts.to_json_dict()
                if self.test_false_alerts
                else None
            ),
            "mean_prediction_latency_ms": self.mean_prediction_latency_ms,
            "p95_prediction_latency_ms": self.p95_prediction_latency_ms,
        }


def _row_sequence_comparison(
    dataset: ExperimentDataset,
    mask: np.ndarray,
    predictions: np.ndarray,
    y_true: np.ndarray,
) -> RowSequenceComparisonPoint:
    return RowSequenceComparisonPoint(
        multiclass_metrics=compute_multiclass_metrics(y_true, predictions),
        detection=evaluate_row_sequence_detection(dataset, mask, predictions),
        false_alerts=compute_row_sequence_false_alerts(dataset, mask, predictions),
    )


def run_alert_policy_experiment(
    dataset: ExperimentDataset,
) -> AlertPolicyExperimentResult:
    train_mask = dataset.split_mask("train")
    val_mask = dataset.split_mask("validation")
    test_mask = dataset.split_mask("test")

    x_train = dataset.X_group(BASE_FEATURE_GROUP, train_mask)
    x_val = dataset.X_group(BASE_FEATURE_GROUP, val_mask)
    x_test = dataset.X_group(BASE_FEATURE_GROUP, test_mask)
    y_train = dataset.y[train_mask]
    y_val = dataset.y[val_mask]
    y_test = dataset.y[test_mask]

    # --- 1. Preserve PR168's exact pipeline (spec section 1) ----------------
    pipeline = build_logistic_regression_pipeline(BASE_LOGISTIC_REGRESSION_C)
    start = time.perf_counter()
    pipeline.fit(x_train, y_train)
    training_seconds = time.perf_counter() - start
    class_order = tuple(pipeline.named_steps["classifier"].classes_)

    proba_val = pipeline.predict_proba(x_val)
    pred_val = pipeline.predict(x_val)
    proba_test = pipeline.predict_proba(x_test)
    pred_test = pipeline.predict(x_test)

    # --- 2. PR168 row-sequence baseline, recomputed on validation -----------
    validation_baseline = _row_sequence_comparison(dataset, val_mask, pred_val, y_val)
    baseline_median = median_latency_seconds(validation_baseline.detection)

    # --- 3. Hysteresis policy search on validation only (spec sections 3+6) -
    policy_search = search_policies(
        dataset,
        val_mask,
        proba_val,
        class_order,
        baseline_median_latency_seconds=baseline_median,
    )
    selected_config = policy_search.selected.config if policy_search.selected else None

    # --- 4. Row-level test metrics: identical to PR168 (spec section 1) ----
    test_multiclass_metrics = compute_multiclass_metrics(y_test, pred_test)
    test_baseline = _row_sequence_comparison(dataset, test_mask, pred_test, y_test)

    # --- 5. Test evaluation of the selected state policy, exactly once -----
    test_detection: DetectionSummary | None = None
    test_false_alerts: FalseAlertSummary | None = None
    if selected_config is not None:
        test_detection = evaluate_detection(
            dataset, test_mask, proba_test, class_order, selected_config
        )
        test_false_alerts = compute_false_alert_summary(
            dataset, test_mask, proba_test, class_order, selected_config
        )

    mean_latency_ms, p95_latency_ms = measure_per_row_prediction_latency_ms(
        pipeline, x_test
    )

    return AlertPolicyExperimentResult(
        class_order=class_order,
        training_seconds=training_seconds,
        validation_baseline=validation_baseline,
        policy_search=policy_search,
        selected_config=selected_config,
        test_multiclass_metrics=test_multiclass_metrics,
        test_baseline=test_baseline,
        test_detection=test_detection,
        test_false_alerts=test_false_alerts,
        test_proba=proba_test,
        mean_prediction_latency_ms=mean_latency_ms,
        p95_prediction_latency_ms=p95_latency_ms,
    )
