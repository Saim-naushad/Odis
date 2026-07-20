"""Calibration-fitting safety (PR169 spec section 11, "Calibration
safety" test group)."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from backend.simulator.dataset.calibration.calibrate import fit_calibrated_model
from backend.simulator.dataset.models.data import load_experiment_dataset


def test_base_pipeline_fit_only_on_train_rows(
    tiny_features_dir: tuple[Path, Path],
) -> None:
    features_dir, _dataset_dir = tiny_features_dir
    dataset = load_experiment_dataset(features_dir)
    train_mask = dataset.split_mask("train")
    val_mask = dataset.split_mask("validation")

    x_train = dataset.X_group("D", train_mask)
    x_val = dataset.X_group("D", val_mask)
    y_train = dataset.y[train_mask]
    y_val = dataset.y[val_mask]

    model = fit_calibrated_model(x_train, y_train, x_val, y_val)

    scaler = model.base_pipeline.named_steps["scaler"]
    np.testing.assert_allclose(scaler.mean_, x_train.mean(axis=0), atol=1e-8)
    np.testing.assert_allclose(scaler.scale_, x_train.std(axis=0), atol=1e-8)


def test_calibrated_probabilities_sum_to_one(
    tiny_features_dir: tuple[Path, Path],
) -> None:
    features_dir, _dataset_dir = tiny_features_dir
    dataset = load_experiment_dataset(features_dir)
    train_mask = dataset.split_mask("train")
    val_mask = dataset.split_mask("validation")
    test_mask = dataset.split_mask("test")

    x_train = dataset.X_group("D", train_mask)
    x_val = dataset.X_group("D", val_mask)
    x_test = dataset.X_group("D", test_mask)
    y_train = dataset.y[train_mask]
    y_val = dataset.y[val_mask]

    model = fit_calibrated_model(x_train, y_train, x_val, y_val)

    for x in (x_train, x_val, x_test):
        proba = model.predict_proba(x)
        np.testing.assert_allclose(proba.sum(axis=1), 1.0, atol=1e-6)
        assert (proba >= 0.0).all()
        assert (proba <= 1.0).all()


def test_class_order_matches_calibrated_and_base_classes(
    tiny_features_dir: tuple[Path, Path],
) -> None:
    features_dir, _dataset_dir = tiny_features_dir
    dataset = load_experiment_dataset(features_dir)
    train_mask = dataset.split_mask("train")
    val_mask = dataset.split_mask("validation")

    x_train = dataset.X_group("D", train_mask)
    x_val = dataset.X_group("D", val_mask)
    y_train = dataset.y[train_mask]
    y_val = dataset.y[val_mask]

    model = fit_calibrated_model(x_train, y_train, x_val, y_val)

    assert model.class_order == tuple(model.calibrated_pipeline.classes_)
    assert model.class_order == tuple(model.base_pipeline.classes_)
    # Never assume healthy-first ordering (PRIMARY_CLASSES' own order) —
    # scikit-learn sorts classes alphabetically.
    assert model.class_order == tuple(sorted(model.class_order))


def test_repeated_fitting_is_deterministic(
    tiny_features_dir: tuple[Path, Path],
) -> None:
    features_dir, _dataset_dir = tiny_features_dir
    dataset = load_experiment_dataset(features_dir)
    train_mask = dataset.split_mask("train")
    val_mask = dataset.split_mask("validation")
    test_mask = dataset.split_mask("test")

    x_train = dataset.X_group("D", train_mask)
    x_val = dataset.X_group("D", val_mask)
    x_test = dataset.X_group("D", test_mask)
    y_train = dataset.y[train_mask]
    y_val = dataset.y[val_mask]

    model_a = fit_calibrated_model(x_train, y_train, x_val, y_val)
    model_b = fit_calibrated_model(x_train, y_train, x_val, y_val)

    proba_a = model_a.predict_proba(x_test)
    proba_b = model_b.predict_proba(x_test)
    np.testing.assert_allclose(proba_a, proba_b)
    assert model_a.class_order == model_b.class_order


def test_uncalibrated_and_calibrated_use_same_class_order(
    tiny_features_dir: tuple[Path, Path],
) -> None:
    features_dir, _dataset_dir = tiny_features_dir
    dataset = load_experiment_dataset(features_dir)
    train_mask = dataset.split_mask("train")
    val_mask = dataset.split_mask("validation")

    x_train = dataset.X_group("D", train_mask)
    x_val = dataset.X_group("D", val_mask)
    y_train = dataset.y[train_mask]
    y_val = dataset.y[val_mask]

    model = fit_calibrated_model(x_train, y_train, x_val, y_val)
    calibrated = model.predict_proba(x_val)
    uncalibrated = model.uncalibrated_predict_proba(x_val)
    assert calibrated.shape == uncalibrated.shape
