"""Deterministic per-`(simulation_run_id, asset_id)` hysteresis state
machine (PR170 spec section 2; `insufficient_data` row handling added by
PR173 spec section 6).

Three confirmed/pending/healthy states only: `healthy`, `pending_<class>`,
`confirmed_<class>` — no persistent `"uncertain"` state (a row whose
diagnosis doesn't satisfy any entry condition simply fails to extend a
streak, exactly like a healthy row would; PR170 has no calibration/
abstention layer, so "uncertain" as a row-level diagnosis does not exist
here at all — see spec section 2's "An optional uncertain row-level
diagnosis may exist, but it must not become a persistent operational
state in this PR").

**Entry**: a candidate class begins tracking the moment a row's own
argmax diagnosis is that (non-healthy) class *and* that class's own
probability meets `entry_probability`. `entry_persistence` consecutive
such rows (same class, still qualifying) confirm it. Any interruption
(different diagnosis, or the same diagnosis dropping below threshold)
resets the candidate to zero — a fresh streak, never a partial carry-over.

**Exit**: once confirmed, a *separate* counter tracks consecutive rows
with `P(healthy) >= healthy_exit_probability`, independent of what the
row's diagnosis is. `exit_persistence` consecutive such rows clears the
confirmed state back to `healthy`.

**Class switch**: while confirmed as class `C`, a different qualifying
class `C'` must independently satisfy its own `entry_persistence`-long
streak (tracked the same way as the healthy-state entry candidate) before
`confirmed_C -> confirmed_C'` fires as a `class_change` event. It does
**not** wait for `C` to exit to `healthy` first.

**Simultaneous exit/switch tie-break**: if both the exit streak and a
switch-candidate streak reach their target on the same row, exit to
`healthy` wins (checked first) — a documented, deterministic, and
conservative choice (never switches into a new confirmed class without
first observing the option of a clean return to healthy).

**`insufficient_data` rows** (PR173): a row this FSM cannot trust (the
feature pipeline's `features/safety.py` rejection contract — see
`ood.alert_metrics` for how a batch of feature-eligible timestamps with
some rejected is turned into this per-row flag) never advances the FSM's
own evidence-gathering counters, and is reported as its own row state,
never silently folded into `healthy`, `pending_*`, or `confirmed_*|`:

- while `healthy`: breaks any in-progress pending-confirmation streak
  (`pending_class`/`pending_streak` reset to `None`/0) — bad input cannot
  itself start or continue building toward a false alert.
- while `confirmed_<C>`: the confirmed state is preserved unchanged and
  no counter advances (exit-persistence and any switch-candidate streak
  are neither incremented nor reset) — bad input cannot itself clear a
  real alert, nor can it be exploited to bridge two otherwise-
  disconnected switch-candidate streaks.

No event is ever emitted for an `insufficient_data` row itself. This
parameter is opt-in (`row_valid=None` reproduces the exact PR170 behavior
byte-for-bit, since every existing caller's rows are implicitly all
valid) precisely so this same function can serve both today's batch
evaluation and a future streaming caller without divergent behavior
(spec section 5).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np

from backend.simulator.dataset.models.config import HEALTHY_LABEL

HEALTHY_STATE = HEALTHY_LABEL
INSUFFICIENT_DATA_STATE = "insufficient_data"


@dataclass(frozen=True)
class StateMachineConfig:
    entry_probability: float
    entry_persistence: int
    healthy_exit_probability: float
    exit_persistence: int

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "entry_probability": self.entry_probability,
            "entry_persistence": self.entry_persistence,
            "healthy_exit_probability": self.healthy_exit_probability,
            "exit_persistence": self.exit_persistence,
        }


@dataclass(frozen=True)
class AlertEvent:
    elapsed_sim_seconds: float
    event_type: str
    """`"new_alert"` (healthy -> confirmed_C), `"class_change"`
    (confirmed_C -> confirmed_C'), or `"cleared"` (confirmed_C -> healthy)."""
    from_state: str
    to_state: str
    fault_class: str | None
    """The class entered (`new_alert`/`class_change`) or exited
    (`cleared`) — `None` is never used; every event involves exactly one
    fault class."""

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "elapsed_sim_seconds": self.elapsed_sim_seconds,
            "event_type": self.event_type,
            "from_state": self.from_state,
            "to_state": self.to_state,
            "fault_class": self.fault_class,
        }


@dataclass(frozen=True)
class StateMachineResult:
    row_states: list[str]
    events: list[AlertEvent]


def _confirmed_state(fault_class: str) -> str:
    return f"confirmed_{fault_class}"


def _pending_state(fault_class: str) -> str:
    return f"pending_{fault_class}"


def run_state_machine(
    elapsed_sim_seconds: Sequence[float],
    proba: np.ndarray,
    classes: tuple[str, ...],
    config: StateMachineConfig,
    *,
    row_valid: Sequence[bool] | None = None,
) -> StateMachineResult:
    """Run the FSM over one `(run, asset)`'s row sequence, in ascending
    elapsed-time order, starting fresh at `healthy` (state is never
    carried across runs or assets — see the module docstring).

    `row_valid[i] is False` marks that row `insufficient_data` (see the
    module docstring for the exact policy); omit `row_valid` entirely (or
    pass all-`True`) to reproduce PR170's original behavior exactly.
    `proba[i]` is still required to be a well-formed row even when
    `row_valid[i] is False` — its content is simply never read for that
    row.
    """
    healthy_index = classes.index(HEALTHY_STATE)

    row_states: list[str] = []
    events: list[AlertEvent] = []

    state = HEALTHY_STATE
    confirmed_class: str | None = None

    pending_class: str | None = None
    pending_streak = 0

    exit_streak = 0
    switch_class: str | None = None
    switch_streak = 0

    validity = row_valid if row_valid is not None else [True] * len(proba)

    for t, row, valid in zip(elapsed_sim_seconds, proba, validity, strict=True):
        if not valid:
            if state == HEALTHY_STATE:
                pending_class = None
                pending_streak = 0
            row_states.append(INSUFFICIENT_DATA_STATE)
            continue

        diag_index = int(np.argmax(row))
        diag = classes[diag_index]
        diag_prob = float(row[diag_index])
        healthy_prob = float(row[healthy_index])
        qualifies = diag != HEALTHY_STATE and diag_prob >= config.entry_probability

        if state == HEALTHY_STATE:
            if qualifies:
                if diag == pending_class:
                    pending_streak += 1
                else:
                    pending_class = diag
                    pending_streak = 1
            else:
                pending_class = None
                pending_streak = 0

            if pending_class is not None and pending_streak >= config.entry_persistence:
                events.append(
                    AlertEvent(
                        t,
                        "new_alert",
                        HEALTHY_STATE,
                        _confirmed_state(pending_class),
                        pending_class,
                    )
                )
                state = _confirmed_state(pending_class)
                confirmed_class = pending_class
                pending_class = None
                pending_streak = 0
                exit_streak = 0
                switch_class = None
                switch_streak = 0
                row_states.append(state)
            else:
                if pending_class is None:
                    row_states.append(HEALTHY_STATE)
                else:
                    row_states.append(_pending_state(pending_class))
            continue

        # state is confirmed_<confirmed_class>
        assert confirmed_class is not None
        healthy_evidence = healthy_prob >= config.healthy_exit_probability
        exit_streak = exit_streak + 1 if healthy_evidence else 0

        switch_candidate = diag != confirmed_class and qualifies
        if switch_candidate:
            switch_streak = switch_streak + 1 if diag == switch_class else 1
            switch_class = diag
        else:
            switch_class = None
            switch_streak = 0

        if exit_streak >= config.exit_persistence:
            events.append(
                AlertEvent(
                    t,
                    "cleared",
                    _confirmed_state(confirmed_class),
                    HEALTHY_STATE,
                    confirmed_class,
                )
            )
            state = HEALTHY_STATE
            confirmed_class = None
            pending_class = None
            pending_streak = 0
            switch_class = None
            switch_streak = 0
            row_states.append(HEALTHY_STATE)
        elif switch_class is not None and switch_streak >= config.entry_persistence:
            events.append(
                AlertEvent(
                    t, "class_change", _confirmed_state(confirmed_class),
                    _confirmed_state(switch_class), switch_class,
                )
            )
            confirmed_class = switch_class
            state = _confirmed_state(confirmed_class)
            exit_streak = 0
            switch_class = None
            switch_streak = 0
            row_states.append(state)
        else:
            row_states.append(state)

    return StateMachineResult(row_states=row_states, events=events)
