"""Stateful per-asset inference session (PR176 spec section 5).

`FaultInferenceSession` retains only a bounded ring buffer (at most
`config.LONGEST_WINDOW_SAMPLES` = 12 entries per measurement) plus a
handful of `O(1)` counters (`alert_policy.state_machine.AlertMachineState`)
— never the full sample history. It calls `features.row.compute_feature_row`
— the exact function the offline batch builder also calls — so a feature
vector computed here from a replayed sequence matches the corresponding
offline `features.parquet` row exactly (see `docs/runtime-inference.md`).

**Elapsed-time convention**: like every offline run, feature/alert
computation is driven by a synthetic `elapsed_sim_seconds` clock that
advances by exactly `config.DT_SECONDS` per ingested sample (`(n+1) *
DT_SECONDS` for the n-th zero-indexed sample, matching `runner.
iter_samples`'s "no pre-tick sample at elapsed=0" convention) — never by
the real gap between two samples' wall-clock `timestamp`s. `timestamp` is
used only to detect non-monotonic input and to stamp the returned result;
this session assumes (does not measure) a fixed-cadence input stream, the
same fixed-cadence assumption `features.builder.UnsupportedCadenceError`
enforces offline.

**Thread-safety**: a `FaultInferenceSession` (and `FaultInferenceManager`)
is not thread-safe. One session must only ever be driven by one caller at
a time; a manager serving multiple assets from multiple threads must
synchronize externally (e.g. one lock per asset, or a single-threaded
consumer per asset) — no locking is implemented here.

**Restart semantics**: a new session/manager always starts cold — warm-up
and alert state reset to their initial values. Cross-process state
persistence/restoration is explicitly out of scope for this PR (spec
section 10); a future Kafka integration must decide whether to restore
state (e.g. from a compacted topic or snapshot) or accept a restart's
brief warm-up/re-detection window.
"""

from __future__ import annotations

from datetime import datetime

import numpy as np

from backend.simulator.dataset.alert_policy.state_machine import (
    AlertMachineState,
    step_state_machine,
)
from backend.simulator.dataset.features.config import (
    DEFAULT_MEASUREMENTS,
    DT_SECONDS,
    LONGEST_WINDOW_SAMPLES,
)
from backend.simulator.dataset.features.row import compute_feature_row
from backend.simulator.inference.evidence import build_evidence
from backend.simulator.inference.loader import PromotedFaultSystem
from backend.simulator.inference.result import InferenceResult, InferenceStatus
from backend.simulator.inference.telemetry import (
    NonMonotonicTimestampError,
    TelemetrySample,
)

_HISTORY_MEASUREMENTS: tuple[str, ...] = DEFAULT_MEASUREMENTS


class FaultInferenceSession:
    """One asset's incremental inference state. Construct via
    `FaultInferenceManager.session_for` in normal use; direct construction
    is for tests and single-asset callers."""

    def __init__(self, *, asset_id: str, system: PromotedFaultSystem) -> None:
        if not asset_id:
            raise ValueError("asset_id must not be empty")
        self._asset_id = asset_id
        self._system = system
        self._reset_state()

    # --- lifecycle -----------------------------------------------------

    def _reset_state(self) -> None:
        self._history: dict[str, list[tuple[float, float]]] = {
            m: [] for m in _HISTORY_MEASUREMENTS
        }
        self._sample_count = 0
        self._last_timestamp: datetime | None = None
        self._machine_state = AlertMachineState()

    def reset(self) -> None:
        """Clears warm-up history and alert state back to a cold start —
        the artifact/system this session scores against is unchanged."""
        self._reset_state()

    @property
    def asset_id(self) -> str:
        return self._asset_id

    @property
    def alert_state(self) -> str:
        return self._machine_state.state

    @property
    def samples_ingested(self) -> int:
        return self._sample_count

    @property
    def samples_required(self) -> int:
        return LONGEST_WINDOW_SAMPLES

    # --- ingestion -------------------------------------------------------

    def ingest(self, sample: TelemetrySample) -> InferenceResult:
        if sample.asset_id != self._asset_id:
            raise ValueError(
                f"sample asset_id {sample.asset_id!r} does not match this "
                f"session's asset_id {self._asset_id!r}"
            )
        if (
            self._last_timestamp is not None
            and sample.timestamp <= self._last_timestamp
        ):
            raise NonMonotonicTimestampError(
                self._asset_id, self._last_timestamp, sample.timestamp
            )

        elapsed = (self._sample_count + 1) * DT_SECONDS
        for measurement in _HISTORY_MEASUREMENTS:
            series = self._history[measurement]
            series.append((elapsed, sample.values[measurement]))
            if len(series) > LONGEST_WINDOW_SAMPLES:
                del series[: len(series) - LONGEST_WINDOW_SAMPLES]

        self._sample_count += 1
        self._last_timestamp = sample.timestamp

        required = LONGEST_WINDOW_SAMPLES
        if self._sample_count < required:
            return InferenceResult(
                status=InferenceStatus.WARMING_UP,
                asset_id=self._asset_id,
                timestamp=sample.timestamp,
                samples_available=self._sample_count,
                samples_required=required,
            )

        index = len(self._history[_HISTORY_MEASUREMENTS[0]]) - 1
        current_values = {m: self._history[m][index][1] for m in _HISTORY_MEASUREMENTS}
        previous_values = {
            m: self._history[m][index - 1][1] for m in _HISTORY_MEASUREMENTS
        }
        row_key = ("runtime", self._asset_id, elapsed)
        row_result = compute_feature_row(
            current_values=current_values,
            previous_values=previous_values,
            series_by_measurement=self._history,
            index=index,
            row_key=row_key,
        )

        if row_result.validity.status == "insufficient_data":
            self._machine_state, _row_state, _event = step_state_machine(
                self._machine_state,
                elapsed_sim_seconds=elapsed,
                proba=np.zeros(len(self._system.class_order)),
                classes=self._system.class_order,
                config=self._system.alert_policy_config,
                valid=False,
            )
            return InferenceResult(
                status=InferenceStatus.INSUFFICIENT_DATA,
                asset_id=self._asset_id,
                timestamp=sample.timestamp,
                alert_state=self._machine_state.state,
                reason_codes=tuple(row_result.validity.reason_codes),
                invalid_feature_names=tuple(row_result.validity.invalid_feature_names),
            )

        feature_vector = np.array(
            [[row_result.values[name] for name in self._system.feature_order]]
        )
        proba = self._system.pipeline.predict_proba(feature_vector)[0]
        class_order = self._system.class_order
        diagnosed_index = int(np.argmax(proba))
        diagnosed_class = class_order[diagnosed_index]
        class_probabilities = {
            cls: float(p) for cls, p in zip(class_order, proba, strict=True)
        }
        maximum_probability = float(proba[diagnosed_index])

        self._machine_state, _row_state, event = step_state_machine(
            self._machine_state,
            elapsed_sim_seconds=elapsed,
            proba=proba,
            classes=class_order,
            config=self._system.alert_policy_config,
            valid=True,
        )

        evidence = build_evidence(
            feature_values=row_result.values,
            class_probabilities=class_probabilities,
            diagnosed_class=diagnosed_class,
            machine_state=self._machine_state,
            config=self._system.alert_policy_config,
        )

        return InferenceResult(
            status=InferenceStatus.VALID_PREDICTION,
            asset_id=self._asset_id,
            timestamp=sample.timestamp,
            diagnosed_class=diagnosed_class,
            class_probabilities=class_probabilities,
            maximum_probability=maximum_probability,
            alert_state=self._machine_state.state,
            alert_event=event.to_json_dict() if event is not None else None,
            evidence=evidence,
            model_system_version=self._system.system_version,
            model_hash=self._system.model_hash,
            policy_hash=self._system.policy_hash,
            feature_schema_version=self._system.feature_schema_version,
        )


class FaultInferenceManager:
    """Owns one `FaultInferenceSession` per `asset_id`, all scored against
    the same loaded `PromotedFaultSystem` — the smallest design a future
    multi-asset Kafka consumer can use safely (spec section 5): route each
    incoming sample by its own `asset_id`, nothing more."""

    def __init__(self, *, system: PromotedFaultSystem) -> None:
        self._system = system
        self._sessions: dict[str, FaultInferenceSession] = {}

    def session_for(self, asset_id: str) -> FaultInferenceSession:
        session = self._sessions.get(asset_id)
        if session is None:
            session = FaultInferenceSession(asset_id=asset_id, system=self._system)
            self._sessions[asset_id] = session
        return session

    def ingest(self, sample: TelemetrySample) -> InferenceResult:
        return self.session_for(sample.asset_id).ingest(sample)

    def reset(self, asset_id: str | None = None) -> None:
        if asset_id is None:
            for session in self._sessions.values():
                session.reset()
            return
        self.session_for(asset_id).reset()

    @property
    def asset_ids(self) -> tuple[str, ...]:
        return tuple(self._sessions)
