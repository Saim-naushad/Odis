"""Preprocessing is fit on the training split only (PR168 spec section 13,
"Leakage protection": "train-only preprocessing fit", "validation/test
rows never enter fitting")."""

from __future__ import annotations

import numpy as np

from backend.simulator.dataset.models.pipelines import (
    balanced_sample_weight,
    build_histogram_gb_pipeline,
    build_logistic_regression_pipeline,
    fit_histogram_gb,
)


def test_standard_scaler_statistics_come_from_train_split_only() -> None:
    rng = np.random.default_rng(0)
    x_train = rng.normal(loc=0.0, scale=1.0, size=(200, 3))
    # Validation/test drawn from a very different distribution — if the
    # scaler were fit on the combined data, its mean/scale would shift
    # toward these values.
    x_val = rng.normal(loc=100.0, scale=50.0, size=(50, 3))

    y_train = np.array(["healthy", "cooling_degradation"] * 100)

    pipeline = build_logistic_regression_pipeline(c=1.0)
    pipeline.fit(x_train, y_train)

    scaler = pipeline.named_steps["scaler"]
    np.testing.assert_allclose(scaler.mean_, x_train.mean(axis=0), atol=1e-8)
    np.testing.assert_allclose(scaler.scale_, x_train.std(axis=0), atol=1e-8)

    # Calling predict on validation data must not refit or mutate the
    # scaler's learned statistics.
    pipeline.predict(x_val)
    np.testing.assert_allclose(scaler.mean_, x_train.mean(axis=0), atol=1e-8)


def test_logistic_regression_uses_balanced_class_weight() -> None:
    pipeline = build_logistic_regression_pipeline(c=1.0)
    assert pipeline.named_steps["classifier"].class_weight == "balanced"


def test_histogram_gb_has_no_standardization_step() -> None:
    pipeline = build_histogram_gb_pipeline(
        learning_rate=0.1, max_leaf_nodes=31, min_samples_leaf=20, l2_regularization=0.0
    )
    assert "scaler" not in pipeline.named_steps
    assert list(pipeline.named_steps) == ["classifier"]


def test_balanced_sample_weight_upweights_rare_classes() -> None:
    y_train = np.array(["healthy"] * 90 + ["cooling_degradation"] * 10)
    weights = balanced_sample_weight(y_train)
    healthy_weight = weights[0]
    rare_weight = weights[-1]
    assert rare_weight > healthy_weight


def test_fit_histogram_gb_passes_sample_weight_and_fits() -> None:
    rng = np.random.default_rng(1)
    x_train = rng.normal(size=(60, 3))
    y_train = np.array(["healthy"] * 50 + ["cooling_degradation"] * 10)
    pipeline = build_histogram_gb_pipeline(
        learning_rate=0.1, max_leaf_nodes=15, min_samples_leaf=5, l2_regularization=0.0
    )
    fitted = fit_histogram_gb(pipeline, x_train, y_train)
    predictions = fitted.predict(x_train)
    assert len(predictions) == len(y_train)
