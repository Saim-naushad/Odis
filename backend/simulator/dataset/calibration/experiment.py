"""Top-level PR169 orchestration: calibration, abstention, and alert-policy
selection, then one untouched test evaluation.

Pure computation over an already-loaded `ExperimentDataset` — no
filesystem writes here (mirrors `models/experiment.py` vs. `models/
generate.py`'s split). Every decision (calibration method is fixed by
config, but the confidence threshold and persistence count are searched)
is made from validation data alone; test-split rows are read exactly
once, in the final section of `run_calibration_experiment`.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import numpy as np

from backend.simulator.dataset.calibration.abstention import (
    CoverageMetrics,
    compute_coverage_metrics,
    diagnose,
)
from backend.simulator.dataset.calibration.alert_policy import (
    AlertPolicySummary,
    evaluate_alert_policy,
)
from backend.simulator.dataset.calibration.calibrate import (
    CalibratedModel,
    fit_calibrated_model,
)
from backend.simulator.dataset.calibration.calibration_metrics import (
    CalibrationMetrics,
    compute_calibration_metrics,
)
from backend.simulator.dataset.calibration.config import (
    BASE_FEATURE_GROUP,
    CONFIDENCE_THRESHOLD_GRID,
)
from backend.simulator.dataset.calibration.policy_search import (
    PolicySearchResult,
    search_policies,
)
from backend.simulator.dataset.calibration.uncertainty_analysis import (
    ConfidenceRankingShift,
    UncertaintyReport,
    compute_confidence_ranking_shift,
    compute_uncertainty_report,
)
from backend.simulator.dataset.models.config import (
    DEFAULT_PERSISTENCE_SAMPLES,
    FAULT_CLASSES,
    HEALTHY_LABEL,
)
from backend.simulator.dataset.models.data import ExperimentDataset
from backend.simulator.dataset.models.detection import (
    DetectionSummary,
    evaluate_detection,
)
from backend.simulator.dataset.models.metrics import (
    MulticlassMetrics,
    compute_multiclass_metrics,
)
from backend.simulator.dataset.models.runtime_metrics import (
    measure_per_row_prediction_latency_ms,
)
from backend.simulator.dataset.models.severity import (
    GroupRecall,
    ramp_row_labels,
    recall_by_group,
    severity_band_row_labels,
)


@dataclass(frozen=True)
class PR168BaselineComparison:
    """The PR168-equivalent policy (uncalibrated native predictions, no
    abstention, `N=3` persistence) recomputed fresh from this run's own
    fitted base pipeline — never hardcoded from PR168's own report — so
    the side-by-side comparison always reflects the actual model in this
    dataset, not a stale copy-pasted number."""

    test_multiclass_metrics: MulticlassMetrics
    test_detection: DetectionSummary
    test_false_positive_rate_healthy: float

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "persistence_samples": DEFAULT_PERSISTENCE_SAMPLES,
            "multiclass": self.test_multiclass_metrics.to_json_dict(),
            "detection": self.test_detection.to_json_dict(),
            "false_positive_rate_healthy": self.test_false_positive_rate_healthy,
        }


@dataclass(frozen=True)
class CalibrationClassificationImpact:
    """Isolates calibration's own effect on *classification* (never mind
    abstention or persistence): scikit-learn's multiclass sigmoid
    calibration fits an independent one-vs-rest curve per class and then
    renormalizes — unlike binary Platt scaling, this does **not**
    guarantee the argmax class is preserved. Measured directly (not
    assumed) because it materially changes the row-level accuracy
    story — see the module docstring and spec section 3's "do not claim
    calibration improved merely because accuracy stayed the same" from
    the opposite direction: here, accuracy did **not** stay the same."""

    argmax_flip_rate: float
    """Fraction of test rows where the calibrated argmax class differs
    from the uncalibrated (base pipeline) argmax class."""
    calibrated_argmax_balanced_accuracy: float
    """Balanced accuracy of the calibrated pipeline's own argmax, with no
    abstention applied — isolates calibration's effect from abstention's."""

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "argmax_flip_rate": self.argmax_flip_rate,
            "calibrated_argmax_balanced_accuracy": (
                self.calibrated_argmax_balanced_accuracy
            ),
        }


@dataclass(frozen=True)
class CalibrationExperimentResult:
    calibrated_model: CalibratedModel
    training_seconds: float
    pr168_baseline: PR168BaselineComparison
    calibration_classification_impact: CalibrationClassificationImpact

    validation_calibration_metrics_before: CalibrationMetrics
    validation_calibration_metrics_after: CalibrationMetrics
    confidence_ranking_shift: ConfidenceRankingShift

    validation_coverage_grid: list[CoverageMetrics]
    policy_search: PolicySearchResult
    selected_confidence_threshold: float
    selected_persistence_samples: int
    validation_uncertainty: UncertaintyReport

    test_multiclass_metrics: MulticlassMetrics
    """Computed over covered (non-`"uncertain"`) test rows only."""
    test_coverage: CoverageMetrics
    test_alert_summary: AlertPolicySummary
    test_uncertainty: UncertaintyReport
    test_severity_recall: dict[str, list[GroupRecall]]
    test_ramp_recall: dict[str, list[GroupRecall]]

    mean_prediction_latency_ms: float
    p95_prediction_latency_ms: float


def run_calibration_experiment(
    dataset: ExperimentDataset,
) -> CalibrationExperimentResult:
    train_mask = dataset.split_mask("train")
    val_mask = dataset.split_mask("validation")
    test_mask = dataset.split_mask("test")

    x_train = dataset.X_group(BASE_FEATURE_GROUP, train_mask)
    x_val = dataset.X_group(BASE_FEATURE_GROUP, val_mask)
    x_test = dataset.X_group(BASE_FEATURE_GROUP, test_mask)
    y_train = dataset.y[train_mask]
    y_val = dataset.y[val_mask]
    y_test = dataset.y[test_mask]

    # --- 1. Fit base pipeline (train) + sigmoid calibrator (validation) ----
    start = time.perf_counter()
    calibrated_model = fit_calibrated_model(x_train, y_train, x_val, y_val)
    training_seconds = time.perf_counter() - start
    class_order = calibrated_model.class_order

    # --- 2. Calibration-quality metrics, before vs. after (spec section 3) -
    proba_val_before = calibrated_model.uncalibrated_predict_proba(x_val)
    proba_val_after = calibrated_model.predict_proba(x_val)
    validation_calibration_metrics_before = compute_calibration_metrics(
        y_val, proba_val_before, class_order
    )
    validation_calibration_metrics_after = compute_calibration_metrics(
        y_val, proba_val_after, class_order
    )
    confidence_ranking_shift = compute_confidence_ranking_shift(
        proba_val_before, proba_val_after, class_order
    )

    # --- 3. Abstention threshold grid on validation (spec section 4) -------
    validation_coverage_grid = [
        compute_coverage_metrics(
            y_val,
            diagnose(proba_val_after, class_order, confidence_threshold=threshold),
            confidence_threshold=threshold,
        )
        for threshold in CONFIDENCE_THRESHOLD_GRID
    ]

    # --- 4. Alert-policy search on validation (spec sections 5-6) ----------
    policy_search = search_policies(dataset, val_mask, proba_val_after, class_order)
    selected = policy_search.selected
    selected_threshold = selected.confidence_threshold
    selected_persistence = selected.persistence_samples

    validation_diagnosis = diagnose(
        proba_val_after, class_order, confidence_threshold=selected_threshold
    )
    validation_confidence = proba_val_after.max(axis=1)
    validation_uncertainty = compute_uncertainty_report(
        dataset, val_mask, validation_diagnosis, validation_confidence
    )

    # --- 5. Test evaluation, exactly once (spec section 8) ------------------
    proba_test = calibrated_model.predict_proba(x_test)
    test_diagnosis = diagnose(
        proba_test, class_order, confidence_threshold=selected_threshold
    )
    test_confidence = proba_test.max(axis=1)

    covered_test = test_diagnosis != "uncertain"
    if covered_test.any():
        test_multiclass_metrics = compute_multiclass_metrics(
            y_test[covered_test], test_diagnosis[covered_test]
        )
    else:
        test_multiclass_metrics = compute_multiclass_metrics(
            y_test[:0], test_diagnosis[:0]
        )

    test_coverage = compute_coverage_metrics(
        y_test, test_diagnosis, confidence_threshold=selected_threshold
    )
    test_alert_summary = evaluate_alert_policy(
        dataset,
        test_mask,
        test_diagnosis,
        confidence_threshold=selected_threshold,
        persistence_samples=selected_persistence,
    )
    test_uncertainty = compute_uncertainty_report(
        dataset, test_mask, test_diagnosis, test_confidence
    )

    severity_labels_test = severity_band_row_labels(dataset)[test_mask]
    ramp_labels_test = ramp_row_labels(dataset)[test_mask]
    run_ids_test = dataset.run_ids[test_mask]
    test_severity_recall = {
        fault_class: recall_by_group(
            y_true=y_test,
            y_pred=test_diagnosis,
            group_labels=severity_labels_test,
            run_ids=run_ids_test,
            target_class=fault_class,
        )
        for fault_class in FAULT_CLASSES
    }
    test_ramp_recall = {
        fault_class: recall_by_group(
            y_true=y_test,
            y_pred=test_diagnosis,
            group_labels=ramp_labels_test,
            run_ids=run_ids_test,
            target_class=fault_class,
        )
        for fault_class in FAULT_CLASSES
    }

    mean_latency_ms, p95_latency_ms = measure_per_row_prediction_latency_ms(
        calibrated_model.calibrated_pipeline, x_test
    )

    # --- 6. PR168-equivalent baseline, recomputed fresh for comparison ------
    pr168_predictions = calibrated_model.base_pipeline.predict(x_test)
    pr168_multiclass_metrics = compute_multiclass_metrics(y_test, pr168_predictions)
    pr168_detection = evaluate_detection(
        dataset,
        test_mask,
        pr168_predictions,
        persistence_samples=DEFAULT_PERSISTENCE_SAMPLES,
    )
    pr168_healthy_mask = y_test == HEALTHY_LABEL
    pr168_false_positive_rate = (
        float((pr168_predictions[pr168_healthy_mask] != HEALTHY_LABEL).mean())
        if pr168_healthy_mask.any()
        else 0.0
    )
    pr168_baseline = PR168BaselineComparison(
        test_multiclass_metrics=pr168_multiclass_metrics,
        test_detection=pr168_detection,
        test_false_positive_rate_healthy=pr168_false_positive_rate,
    )

    calibrated_argmax_index = proba_test.argmax(axis=1)
    calibrated_argmax = np.array(class_order, dtype=object)[calibrated_argmax_index]
    argmax_flip_rate = float((calibrated_argmax != pr168_predictions).mean())
    calibrated_argmax_balanced_accuracy = compute_multiclass_metrics(
        y_test, calibrated_argmax
    ).balanced_accuracy
    calibration_classification_impact = CalibrationClassificationImpact(
        argmax_flip_rate=argmax_flip_rate,
        calibrated_argmax_balanced_accuracy=calibrated_argmax_balanced_accuracy,
    )

    return CalibrationExperimentResult(
        calibrated_model=calibrated_model,
        training_seconds=training_seconds,
        pr168_baseline=pr168_baseline,
        calibration_classification_impact=calibration_classification_impact,
        validation_calibration_metrics_before=validation_calibration_metrics_before,
        validation_calibration_metrics_after=validation_calibration_metrics_after,
        confidence_ranking_shift=confidence_ranking_shift,
        validation_coverage_grid=validation_coverage_grid,
        policy_search=policy_search,
        selected_confidence_threshold=selected_threshold,
        selected_persistence_samples=selected_persistence,
        validation_uncertainty=validation_uncertainty,
        test_multiclass_metrics=test_multiclass_metrics,
        test_coverage=test_coverage,
        test_alert_summary=test_alert_summary,
        test_uncertainty=test_uncertainty,
        test_severity_recall=test_severity_recall,
        test_ramp_recall=test_ramp_recall,
        mean_prediction_latency_ms=mean_latency_ms,
        p95_prediction_latency_ms=p95_latency_ms,
    )
