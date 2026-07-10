"""Export a simple linear-drift ONNX model for architecture validation.

The model extrapolates the last observed slope across the forecast horizon:

    slope = context[-1] - context[-2]
    forecast[i] = context[-1] + slope * (i + 1)

This is intentionally simple. Production models can replace the ONNX artifact
without changing application code as long as they honor the same input/output
contract (``context`` float32[batch, 24] -> ``forecast`` float32[batch, 12]).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import onnx
from onnx import TensorProto, helper, numpy_helper

CONTEXT_LENGTH = 24
HORIZON_STEPS = 12
MODEL_VERSION = 13


def build_persistence_drift_graph() -> onnx.ModelProto:
    """Build an ONNX graph for linear drift extrapolation."""
    context = helper.make_tensor_value_info(
        "context",
        TensorProto.FLOAT,
        [None, CONTEXT_LENGTH],
    )
    forecast = helper.make_tensor_value_info(
        "forecast",
        TensorProto.FLOAT,
        [None, HORIZON_STEPS],
    )

    prev_index = numpy_helper.from_array(
        np.array([CONTEXT_LENGTH - 2], dtype=np.int64),
        name="prev_index",
    )
    last_index = numpy_helper.from_array(
        np.array([CONTEXT_LENGTH - 1], dtype=np.int64),
        name="last_index",
    )
    steps = numpy_helper.from_array(
        np.arange(1, HORIZON_STEPS + 1, dtype=np.float32),
        name="steps",
    )

    nodes = [
        helper.make_node(
            "Gather",
            ["context", "prev_index"],
            ["previous_value"],
            axis=1,
        ),
        helper.make_node(
            "Gather",
            ["context", "last_index"],
            ["last_value"],
            axis=1,
        ),
        helper.make_node("Sub", ["last_value", "previous_value"], ["slope"]),
        helper.make_node("Mul", ["slope", "steps"], ["scaled_steps"]),
        helper.make_node("Add", ["last_value", "scaled_steps"], ["forecast"]),
    ]

    graph = helper.make_graph(
        nodes,
        "persistence_drift_v1",
        [context],
        [forecast],
        initializer=[prev_index, last_index, steps],
    )
    model = helper.make_model(
        graph,
        opset_imports=[helper.make_opsetid("", MODEL_VERSION)],
    )
    onnx.checker.check_model(model)
    return model


def export_model(output_path: Path) -> None:
    """Write the validation ONNX model to disk."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    model = build_persistence_drift_graph()
    onnx.save(model, output_path)


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    output = (
        repo_root
        / "backend"
        / "app"
        / "infrastructure"
        / "inference"
        / "models"
        / "persistence_drift_v1.onnx"
    )
    export_model(output)
    print(f"Wrote {output}")


if __name__ == "__main__":
    main()
