"""Deterministic evidence payload (PR176 spec section 8).

**Chosen approach: a small, curated, deterministic evidence set — not
SHAP, and not standardized-coefficient attribution.** Coefficient
attribution (`standardized feature value x class coefficient`) is
explicitly allowed by the spec, but doing it correctly requires exactly
reproducing the fitted `StandardScaler`'s per-feature mean/scale and the
logistic-regression classifier's per-class coefficient row/intercept and
class-index mapping — a second correctness-critical parity surface this
PR does not need to open just to explain a diagnosis. A future PR can add
it once evidence needs are sharper; every item below is already computed
as an ordinary part of inference (feature values, class probabilities,
alert-machine counters) — nothing new is computed just to explain.

Deterministic rule, at most `MAX_EVIDENCE_ITEMS` (5) items, always in this
order: (1) the diagnosed/top class's own probability, (2) the runner-up
class's probability (class-probability ranking), (3-4) the two physics
residual features with the largest absolute magnitude (ties broken by
feature name, ascending), (5) alert confirmation/exit progress as a
fraction of the persistence requirement. Steps that don't apply (e.g. no
runner-up class, or the FSM has no in-progress streak) are simply
omitted — never padded with a placeholder.
"""

from __future__ import annotations

from backend.simulator.dataset.alert_policy.state_machine import (
    AlertMachineState,
    StateMachineConfig,
)
from backend.simulator.dataset.features.residuals import RESIDUAL_SPECS
from backend.simulator.dataset.models.config import HEALTHY_LABEL
from backend.simulator.inference.result import EvidenceItem

MAX_EVIDENCE_ITEMS = 5
_RESIDUAL_NAMES: tuple[str, ...] = tuple(spec.name for spec in RESIDUAL_SPECS)
_TOP_N_RESIDUALS = 2


def build_evidence(
    *,
    feature_values: dict[str, float],
    class_probabilities: dict[str, float],
    diagnosed_class: str,
    machine_state: AlertMachineState,
    config: StateMachineConfig,
) -> tuple[EvidenceItem, ...]:
    items: list[EvidenceItem] = []

    ranked_classes = sorted(
        class_probabilities.items(), key=lambda pair: (-pair[1], pair[0])
    )
    top_class, top_probability = ranked_classes[0]
    items.append(
        EvidenceItem(
            label="top_class_probability",
            value=top_probability,
            detail=f"{top_class} (diagnosed: {diagnosed_class})",
        )
    )
    if len(ranked_classes) > 1:
        runner_up_class, runner_up_probability = ranked_classes[1]
        items.append(
            EvidenceItem(
                label="runner_up_class_probability",
                value=runner_up_probability,
                detail=runner_up_class,
            )
        )

    residual_pairs = [
        (name, feature_values[name])
        for name in _RESIDUAL_NAMES
        if name in feature_values
    ]
    residual_pairs.sort(key=lambda pair: (-abs(pair[1]), pair[0]))
    for name, value in residual_pairs[:_TOP_N_RESIDUALS]:
        items.append(
            EvidenceItem(
                label=f"residual:{name}",
                value=value,
                detail="observed minus fixed healthy reference curve",
            )
        )

    progress_item = _alert_progress_evidence(machine_state, config)
    if progress_item is not None:
        items.append(progress_item)

    return tuple(items[:MAX_EVIDENCE_ITEMS])


def _alert_progress_evidence(
    machine_state: AlertMachineState, config: StateMachineConfig
) -> EvidenceItem | None:
    if machine_state.state == HEALTHY_LABEL:
        if machine_state.pending_class is None:
            return None
        return EvidenceItem(
            label="alert_entry_progress",
            value=machine_state.pending_streak / config.entry_persistence,
            detail=(
                f"pending_{machine_state.pending_class}: "
                f"{machine_state.pending_streak}/{config.entry_persistence} "
                "consecutive qualifying samples"
            ),
        )
    return EvidenceItem(
        label="alert_exit_progress",
        value=machine_state.exit_streak / config.exit_persistence,
        detail=(
            f"{machine_state.state}: exit_streak "
            f"{machine_state.exit_streak}/{config.exit_persistence} "
            "consecutive healthy-qualifying samples"
        ),
    )
