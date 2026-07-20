"""Synthetic PR171 evaluation-output fixtures for PR172 `shift_study`
tests.

Builds minimal, valid `ood_evaluation_summary.json` / `feature_shift.json`
/ `error_cases.json` triples directly — no dataset generation, no model
fitting — so every test in this package runs in milliseconds while still
exercising the real `cohort_loading`/`rankings`/`verdict` code paths
against realistic-shaped data (spec section 13: "use tiny summaries...
rather than regenerating all four full cohorts in every test").
"""

from __future__ import annotations

import json
from pathlib import Path

from backend.simulator.dataset.models.config import FAULT_CLASSES, PRIMARY_CLASSES

DEFAULT_PIPELINE_SHA256 = "a" * 64
DEFAULT_ALERT_POLICY_SHA256 = "b" * 64


def _multiclass_metrics(
    *, balanced_accuracy: float, recall_by_class: dict[str, float]
) -> dict:
    per_class = {
        cls: {
            "precision": 0.7,
            "recall": recall_by_class.get(cls, 0.8),
            "f1": 0.7,
            "support": 100,
        }
        for cls in PRIMARY_CLASSES
    }
    n = len(PRIMARY_CLASSES)
    return {
        "balanced_accuracy": balanced_accuracy,
        "macro_precision": 0.7,
        "macro_recall": balanced_accuracy,
        "macro_f1": balanced_accuracy - 0.05,
        "per_class": per_class,
        "confusion_matrix": [[0] * n for _ in range(n)],
        "class_order": list(PRIMARY_CLASSES),
        "support": {cls: 100 for cls in PRIMARY_CLASSES},
    }


def _detection_run_results(
    *,
    any_fault_missed_runs: list[str],
    correct_class_missed_runs: list[str],
    incorrect_class_alert_run_count: int,
) -> list[dict]:
    results = []
    for cls in FAULT_CLASSES:
        for i in range(4):
            run_id = f"{cls}-{i:04d}"
            any_missed = run_id in any_fault_missed_runs
            correct_missed = run_id in correct_class_missed_runs
            results.append(
                {
                    "simulation_run_id": run_id,
                    "fault_class": cls,
                    "fault_start_sim_seconds": 100.0,
                    "correct_class_detected": not correct_missed,
                    "correct_class_latency_seconds": None if correct_missed else 50.0,
                    "any_fault_detected": not any_missed,
                    "any_fault_latency_seconds": None if any_missed else 50.0,
                    "any_fault_class_at_first_detection": None if any_missed else cls,
                    "incorrect_class_confirmed_before_correct": (
                        incorrect_class_alert_run_count > 0
                        and run_id
                        == f"{FAULT_CLASSES[0]}-0000"
                    ),
                    "confirmed_active_at_onset": False,
                    "confirmed_class_at_onset": None,
                }
            )
    return results


def build_cohort_evaluation_dir(
    directory: Path,
    *,
    pipeline_sha256: str = DEFAULT_PIPELINE_SHA256,
    alert_policy_sha256: str = DEFAULT_ALERT_POLICY_SHA256,
    id_balanced_accuracy: float = 0.85,
    ood_balanced_accuracy: float = 0.85,
    id_healthy_fpr: float = 0.08,
    ood_healthy_fpr: float = 0.08,
    ood_recall_by_class: dict[str, float] | None = None,
    false_alert_rate_per_healthy_hour: float = 0.0,
    healthy_runs_with_alert: int = 0,
    any_fault_missed_runs: list[str] | None = None,
    correct_class_missed_runs: list[str] | None = None,
    incorrect_class_alert_run_count: int = 0,
    median_correct_class_latency_seconds: float | None = 100.0,
    detected_within_120s: float = 0.5,
    rejected_row_count: int = 0,
    total_eligible_rows: int = 1000,
    rejected_by_class: dict[str, int] | None = None,
    top_feature_smd: float = 1.0,
) -> Path:
    """Writes a complete, minimal-but-valid PR171/PR173 `ood` evaluation
    output directory under `directory` and returns it."""
    directory.mkdir(parents=True, exist_ok=True)
    any_fault_missed_runs = any_fault_missed_runs or []
    correct_class_missed_runs = correct_class_missed_runs or []
    ood_recall_by_class = ood_recall_by_class or dict.fromkeys(FAULT_CLASSES, 0.8)

    id_metrics = _multiclass_metrics(
        balanced_accuracy=id_balanced_accuracy,
        recall_by_class=dict.fromkeys(FAULT_CLASSES, 0.85),
    )
    ood_metrics = _multiclass_metrics(
        balanced_accuracy=ood_balanced_accuracy, recall_by_class=ood_recall_by_class
    )

    run_results = _detection_run_results(
        any_fault_missed_runs=any_fault_missed_runs,
        correct_class_missed_runs=correct_class_missed_runs,
        incorrect_class_alert_run_count=incorrect_class_alert_run_count,
    )

    rejection_fraction = (
        rejected_row_count / total_eligible_rows if total_eligible_rows > 0 else 0.0
    )
    empty_availability = {
        "valid_feature_coverage": 1.0,
        "insufficient_data_rate": 0.0,
        "insufficient_data_seconds_total": 0.0,
        "longest_consecutive_streak_rows": 0,
        "longest_consecutive_streak_seconds": 0.0,
        "affected_run_count": 0,
        "affected_asset_ids": [],
        "reason_counts": {},
        "class_distribution": {},
        "stage_distribution": {"ramp": 0, "post_ramp": 0, "not_in_fault_window": 0},
        "ramp_unavailable_fraction": None,
        "post_ramp_unavailable_fraction": None,
        "detection_opportunities_interrupted": 0,
    }
    ood_availability = {
        **empty_availability,
        "valid_feature_coverage": 1.0 - rejection_fraction,
        "insufficient_data_rate": rejection_fraction,
        "insufficient_data_seconds_total": rejected_row_count * 10.0,
        "affected_run_count": min(rejected_row_count, 16),
        "class_distribution": rejected_by_class or {},
    }

    summary = {
        "generation_command": "test",
        "frozen_artifacts": {
            "pipeline_sha256": pipeline_sha256,
            "alert_policy_sha256": alert_policy_sha256,
            "model_type": "logistic_regression",
            "feature_group": "D",
            "class_order": list(PRIMARY_CLASSES),
            "state_machine_config": {
                "entry_probability": 0.6,
                "entry_persistence": 4,
                "healthy_exit_probability": 0.5,
                "exit_persistence": 2,
            },
        },
        "id_cohort": {
            "run_count": 16,
            "insufficient_data": {
                "total_eligible_rows": total_eligible_rows,
                "rejected_row_count": 0,
                "rejection_fraction": 0.0,
                "by_reason_code": {},
                "by_invalid_feature_name": {
                    "voltage_per_current": 0,
                    "power_per_fuel_flow": 0,
                },
                "affected_run_count": 0,
                "affected_run_ids": [],
            },
            "availability": empty_availability,
            "diagnosis": {
                "multiclass_metrics": id_metrics,
                "healthy_false_positive_rate": id_healthy_fpr,
                "severity_band_recall": {},
                "ramp_stage_recall": {},
            },
            "alerts": {
                "detection": {
                    "run_results": run_results,
                    "correct_class_missed_runs": [],
                    "any_fault_missed_runs": [],
                    "median_correct_class_latency_seconds": 100.0,
                    "detected_within_seconds": {"30": 0.1, "60": 0.3, "120": 0.5},
                },
                "detected_within_240s": 0.6,
                "false_alerts": {
                    "episodes": [],
                    "false_confirmed_event_count": 0,
                    "false_anomalous_row_count": 0,
                    "healthy_hours_evaluated": 4.0,
                    "false_alert_events_per_healthy_hour": 0.0,
                    "mean_false_episode_duration_seconds": 0.0,
                    "max_false_episode_duration_seconds": 0.0,
                    "healthy_runs_with_alert": 0,
                    "total_healthy_run_segments": 16,
                },
                "incorrect_class_alert_run_count": 0,
            },
        },
        "ood_cohort": {
            "run_count": 16,
            "insufficient_data": {
                "total_eligible_rows": total_eligible_rows,
                "rejected_row_count": rejected_row_count,
                "rejection_fraction": rejection_fraction,
                "by_reason_code": (
                    {"near_zero_denominator": rejected_row_count}
                    if rejected_row_count
                    else {}
                ),
                "by_invalid_feature_name": {
                    "voltage_per_current": 0,
                    "power_per_fuel_flow": rejected_row_count,
                },
                "affected_run_count": min(rejected_row_count, 16),
                "affected_run_ids": [],
            },
            "availability": ood_availability,
            "diagnosis": {
                "multiclass_metrics": ood_metrics,
                "healthy_false_positive_rate": ood_healthy_fpr,
                "severity_band_recall": {},
                "ramp_stage_recall": {
                    cls: [
                        {
                            "group": "ramp",
                            "recall": ood_recall_by_class.get(cls, 0.8) - 0.1,
                            "row_count": 40,
                            "run_count": 4,
                            "small_sample": False,
                        },
                        {
                            "group": "post_ramp",
                            "recall": ood_recall_by_class.get(cls, 0.8) + 0.1,
                            "row_count": 20,
                            "run_count": 4,
                            "small_sample": False,
                        },
                    ]
                    for cls in FAULT_CLASSES
                },
            },
            "alerts": {
                "detection": {
                    "run_results": run_results,
                    "correct_class_missed_runs": correct_class_missed_runs,
                    "any_fault_missed_runs": any_fault_missed_runs,
                    "median_correct_class_latency_seconds": (
                        median_correct_class_latency_seconds
                    ),
                    "detected_within_seconds": {
                        "30": 0.1,
                        "60": 0.3,
                        "120": detected_within_120s,
                    },
                },
                "detected_within_240s": min(detected_within_120s + 0.2, 1.0),
                "false_alerts": {
                    "episodes": [],
                    "false_confirmed_event_count": 0,
                    "false_anomalous_row_count": 0,
                    "healthy_hours_evaluated": 4.0,
                    "false_alert_events_per_healthy_hour": (
                        false_alert_rate_per_healthy_hour
                    ),
                    "mean_false_episode_duration_seconds": 30.0,
                    "max_false_episode_duration_seconds": 60.0,
                    "healthy_runs_with_alert": healthy_runs_with_alert,
                    "total_healthy_run_segments": 16,
                },
                "incorrect_class_alert_run_count": incorrect_class_alert_run_count,
            },
        },
        "comparison": {
            "balanced_accuracy": {
                "id": id_balanced_accuracy,
                "ood": ood_balanced_accuracy,
                "absolute_change": ood_balanced_accuracy - id_balanced_accuracy,
                "relative_change": None,
            },
            "macro_f1": {
                "id": id_metrics["macro_f1"],
                "ood": ood_metrics["macro_f1"],
                "absolute_change": ood_metrics["macro_f1"] - id_metrics["macro_f1"],
                "relative_change": None,
            },
            "healthy_false_positive_rate": {
                "id": id_healthy_fpr,
                "ood": ood_healthy_fpr,
                "absolute_change": ood_healthy_fpr - id_healthy_fpr,
                "relative_change": None,
            },
            "per_class_recall": {},
            "false_alert_events_per_healthy_hour": {
                "id": 0.0,
                "ood": false_alert_rate_per_healthy_hour,
                "absolute_change": false_alert_rate_per_healthy_hour,
                "relative_change": None,
            },
            "any_fault_missed_run_count": {
                "id": 0,
                "ood": len(any_fault_missed_runs),
                "absolute_change": len(any_fault_missed_runs),
                "relative_change": None,
            },
            "correct_class_missed_run_count": {
                "id": 0,
                "ood": len(correct_class_missed_runs),
                "absolute_change": len(correct_class_missed_runs),
                "relative_change": None,
            },
            "median_correct_class_latency_seconds": {
                "id": 100.0,
                "ood": median_correct_class_latency_seconds,
                "absolute_change": None,
                "relative_change": None,
            },
            "detected_within_120s": {
                "id": 0.5,
                "ood": detected_within_120s,
                "absolute_change": detected_within_120s - 0.5,
                "relative_change": None,
            },
        },
        "verdict": {
            "verdict": "GENERALIZES ACCEPTABLY TO OOD V1",
            "reasons": [],
            "criteria_description": "test",
        },
    }
    (directory / "ood_evaluation_summary.json").write_text(json.dumps(summary))

    feature_shift = {
        "feature_count": 153,
        "top_shifted_by_group": {
            "raw": [
                {
                    "name": "stack_temperature",
                    "group": "raw",
                    "standardized_mean_difference": top_feature_smd,
                    "wasserstein_distance": 1.0,
                    "train_mean": 0.0,
                    "train_std": 1.0,
                    "ood_mean": top_feature_smd,
                    "ood_std": 1.0,
                    "train_min": -3.0,
                    "train_max": 3.0,
                    "ood_out_of_range_fraction": 0.1,
                }
            ],
            "temporal": [],
            "cross_signal": [],
            "residual": [],
        },
        "top_shifted_overall": [
            {
                "name": "stack_temperature",
                "group": "raw",
                "standardized_mean_difference": top_feature_smd,
                "wasserstein_distance": 1.0,
                "train_mean": 0.0,
                "train_std": 1.0,
                "ood_mean": top_feature_smd,
                "ood_std": 1.0,
                "train_min": -3.0,
                "train_max": 3.0,
                "ood_out_of_range_fraction": 0.1,
            }
        ],
        "features_with_out_of_range_ood_values": [],
    }
    (directory / "feature_shift.json").write_text(json.dumps(feature_shift))

    error_cases = [
        {
            "category": "successful_easy_fault",
            "simulation_run_id": f"{FAULT_CLASSES[0]}-0000",
            "fault_class": FAULT_CLASSES[0],
            "rationale": "test case",
            "timeline": [
                {
                    "elapsed_sim_seconds": 100.0,
                    "true_label": FAULT_CLASSES[0],
                    "predicted_label": FAULT_CLASSES[0],
                    "predicted_probability": 0.9,
                    "alert_state": f"confirmed_{FAULT_CLASSES[0]}",
                }
            ],
        }
    ]
    (directory / "error_cases.json").write_text(json.dumps(error_cases))

    return directory
