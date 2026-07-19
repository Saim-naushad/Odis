"""Multiclass classification metrics (PR168 spec section 7).

Generic accuracy is deliberately never reported alone — every call site
uses `compute_multiclass_metrics`, which always returns balanced accuracy,
macro precision/recall/F1, the full per-class breakdown, and the
confusion matrix together.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from sklearn.metrics import (
    balanced_accuracy_score,
    confusion_matrix,
    precision_recall_fscore_support,
)

from backend.simulator.dataset.models.config import PRIMARY_CLASSES


@dataclass(frozen=True)
class MulticlassMetrics:
    balanced_accuracy: float
    macro_precision: float
    macro_recall: float
    macro_f1: float
    per_class: dict[str, dict[str, float]]
    confusion_matrix: list[list[int]]
    class_order: tuple[str, ...]
    support: dict[str, int]

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "balanced_accuracy": self.balanced_accuracy,
            "macro_precision": self.macro_precision,
            "macro_recall": self.macro_recall,
            "macro_f1": self.macro_f1,
            "per_class": self.per_class,
            "confusion_matrix": self.confusion_matrix,
            "class_order": list(self.class_order),
            "support": self.support,
        }


def compute_multiclass_metrics(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    *,
    class_order: tuple[str, ...] = PRIMARY_CLASSES,
) -> MulticlassMetrics:
    """All metrics computed over the fixed `class_order` so a class absent
    from a small evaluation slice still appears with zero support rather
    than silently vanishing from the report."""
    balanced_accuracy = float(balanced_accuracy_score(y_true, y_pred))
    precision, recall, f1, support = precision_recall_fscore_support(
        y_true, y_pred, labels=list(class_order), average=None, zero_division=0
    )
    macro_precision, macro_recall, macro_f1, _ = precision_recall_fscore_support(
        y_true, y_pred, labels=list(class_order), average="macro", zero_division=0
    )
    per_class = {
        class_name: {
            "precision": float(precision[i]),
            "recall": float(recall[i]),
            "f1": float(f1[i]),
            "support": int(support[i]),
        }
        for i, class_name in enumerate(class_order)
    }
    cm = confusion_matrix(y_true, y_pred, labels=list(class_order))

    return MulticlassMetrics(
        balanced_accuracy=balanced_accuracy,
        macro_precision=float(macro_precision),
        macro_recall=float(macro_recall),
        macro_f1=float(macro_f1),
        per_class=per_class,
        confusion_matrix=cm.tolist(),
        class_order=class_order,
        support={name: int(support[i]) for i, name in enumerate(class_order)},
    )
