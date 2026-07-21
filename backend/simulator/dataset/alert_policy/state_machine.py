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

**PR176 addition**: `run_state_machine` is a loop over `step_state_machine`,
which carries all per-row FSM state in one explicit, tiny (`O(1)`)
`AlertMachineState` value rather than function-local variables. This is a
pure extraction — `run_state_machine`'s behavior is unchanged (verified by
this module's own test suite) — done so a future incremental/streaming
caller (`backend.simulator.inference`) can hold one `AlertMachineState`
per asset across calls instead of replaying full row history through this
function on every new sample.
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


@dataclass
class AlertMachineState:
    """Every value `step_state_machine` reads and mutates between rows —
    `O(1)` regardless of history length, so a caller (batch or streaming)
    only ever needs to hold one of these per `(run, asset)`, never the row
    history itself. The default (`healthy`, no pending/confirmed class,
    every streak at 0) is the FSM's fresh-start state."""

    state: str = HEALTHY_STATE
    confirmed_class: str | None = None
    pending_class: str | None = None
    pending_streak: int = 0
    exit_streak: int = 0
    switch_class: str | None = None
    switch_streak: int = 0


def step_state_machine(
    machine_state: AlertMachineState,
    *,
    elapsed_sim_seconds: float,
    proba: np.ndarray,
    classes: tuple[str, ...],
    config: StateMachineConfig,
    valid: bool = True,
) -> tuple[AlertMachineState, str, AlertEvent | None]:
    """Advance `machine_state` by exactly one row; returns `(next_state,
    row_state, event_or_none)`. `machine_state` itself is never mutated in
    place — callers hold on to the returned value for the next call.

    This is the one place the FSM's transition rules are defined;
    `run_state_machine` is a thin loop over this function (see module
    docstring) and a future incremental caller uses it identically, one
    sample at a time, carrying `next_state` forward across calls.
    """
    healthy_index = classes.index(HEALTHY_STATE)
    m = machine_state

    if not valid:
        next_pending_class = m.pending_class
        next_pending_streak = m.pending_streak
        if m.state == HEALTHY_STATE:
            next_pending_class = None
            next_pending_streak = 0
        return (
            AlertMachineState(
                state=m.state,
                confirmed_class=m.confirmed_class,
                pending_class=next_pending_class,
                pending_streak=next_pending_streak,
                exit_streak=m.exit_streak,
                switch_class=m.switch_class,
                switch_streak=m.switch_streak,
            ),
            INSUFFICIENT_DATA_STATE,
            None,
        )

    diag_index = int(np.argmax(proba))
    diag = classes[diag_index]
    diag_prob = float(proba[diag_index])
    healthy_prob = float(proba[healthy_index])
    qualifies = diag != HEALTHY_STATE and diag_prob >= config.entry_probability

    if m.state == HEALTHY_STATE:
        if qualifies:
            if diag == m.pending_class:
                pending_class = m.pending_class
                pending_streak = m.pending_streak + 1
            else:
                pending_class = diag
                pending_streak = 1
        else:
            pending_class = None
            pending_streak = 0

        if pending_class is not None and pending_streak >= config.entry_persistence:
            event = AlertEvent(
                elapsed_sim_seconds,
                "new_alert",
                HEALTHY_STATE,
                _confirmed_state(pending_class),
                pending_class,
            )
            next_state = AlertMachineState(
                state=_confirmed_state(pending_class),
                confirmed_class=pending_class,
                pending_class=None,
                pending_streak=0,
                exit_streak=0,
                switch_class=None,
                switch_streak=0,
            )
            return next_state, next_state.state, event

        next_state = AlertMachineState(
            state=HEALTHY_STATE,
            confirmed_class=None,
            pending_class=pending_class,
            pending_streak=pending_streak,
            exit_streak=m.exit_streak,
            switch_class=m.switch_class,
            switch_streak=m.switch_streak,
        )
        row_state = (
            HEALTHY_STATE if pending_class is None else _pending_state(pending_class)
        )
        return next_state, row_state, None

    # state is confirmed_<confirmed_class>
    assert m.confirmed_class is not None
    healthy_evidence = healthy_prob >= config.healthy_exit_probability
    exit_streak = m.exit_streak + 1 if healthy_evidence else 0

    switch_candidate = diag != m.confirmed_class and qualifies
    if switch_candidate:
        switch_streak = m.switch_streak + 1 if diag == m.switch_class else 1
        switch_class = diag
    else:
        switch_class = None
        switch_streak = 0

    if exit_streak >= config.exit_persistence:
        event = AlertEvent(
            elapsed_sim_seconds,
            "cleared",
            _confirmed_state(m.confirmed_class),
            HEALTHY_STATE,
            m.confirmed_class,
        )
        next_state = AlertMachineState(
            state=HEALTHY_STATE,
            confirmed_class=None,
            pending_class=None,
            pending_streak=0,
            exit_streak=0,
            switch_class=None,
            switch_streak=0,
        )
        return next_state, HEALTHY_STATE, event

    if switch_class is not None and switch_streak >= config.entry_persistence:
        event = AlertEvent(
            elapsed_sim_seconds,
            "class_change",
            _confirmed_state(m.confirmed_class),
            _confirmed_state(switch_class),
            switch_class,
        )
        next_state = AlertMachineState(
            state=_confirmed_state(switch_class),
            confirmed_class=switch_class,
            pending_class=None,
            pending_streak=0,
            exit_streak=0,
            switch_class=None,
            switch_streak=0,
        )
        return next_state, next_state.state, event

    next_state = AlertMachineState(
        state=m.state,
        confirmed_class=m.confirmed_class,
        pending_class=m.pending_class,
        pending_streak=m.pending_streak,
        exit_streak=exit_streak,
        switch_class=switch_class,
        switch_streak=switch_streak,
    )
    return next_state, next_state.state, None


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
    row_states: list[str] = []
    events: list[AlertEvent] = []

    machine_state = AlertMachineState()
    validity = row_valid if row_valid is not None else [True] * len(proba)

    for t, row, valid in zip(elapsed_sim_seconds, proba, validity, strict=True):
        machine_state, row_state, event = step_state_machine(
            machine_state,
            elapsed_sim_seconds=t,
            proba=row,
            classes=classes,
            config=config,
            valid=valid,
        )
        row_states.append(row_state)
        if event is not None:
            events.append(event)

    return StateMachineResult(row_states=row_states, events=events)
