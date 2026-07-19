"""Physical-behavior analysis (PR166 spec section 6).

For each fault class, compares the target asset's telemetry immediately
before the fault window (`elapsed_sim_seconds < fault_start`) against
telemetry during it (`fault_start <= elapsed_sim_seconds < fault_end`),
per measurement, across every run of that class. Consistency is reported
honestly (`direction_consistency`), never forced to look like every run
agrees.

Expected signatures come from how the shared physics actually works (see
`backend/simulator/machine.py`, `backend/simulator/telemetry.py`,
`fault_effect.py`):

- `cooling_degradation` lowers `cooling_efficiency`, which raises
  `target_temperature` (less `cooling_bonus` subtracted) and, through
  `target_pressure`'s `-(stack_temperature - 60) * coefficient` term, lowers
  pressure; `coolant_flow`'s formula adds `(0.85 - cooling_efficiency) * 12`,
  so it rises as cooling degrades.
- `hydrogen_supply_issue` lowers `fuel_supply_factor`, which lowers
  `hydrogen_flow` (`fuel_flow`) directly, lowers `current` once the factor
  crosses the starvation threshold, and — via the PR162 starvation penalty —
  lowers `voltage`; `power_output = voltage * current / 1000` inherits both.
- `sensor_anomaly` only ever adds a bias to the *emitted*
  `stack_temperature` observation (`telemetry.core_observations_from_state`);
  it never touches `FuelCellMachineState`, so every other channel — physical
  `stack_pressure` included, which is computed from the machine's own
  internal (unbiased) temperature — should show no coherent shift.

Each expected signature is `hard` (a reversal is `"blocking"`) or soft (a
reversal is only `"concerning"`) — see `_EXPECTED_SIGNATURES`. A signature
that is absent/too weak to detect is always less severe than an outright
reversal, and is classified `"acceptable simulator limitation"` for soft
signatures.
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from backend.simulator.dataset.audit.findings import Finding, Severity
from backend.simulator.dataset.audit.records import DatasetRecords

FAULT_CLASSES = ("cooling_degradation", "hydrogen_supply_issue", "sensor_anomaly")
MEASUREMENTS = (
    "stack_temperature",
    "stack_pressure",
    "current",
    "voltage",
    "fuel_flow",
    "power_output",
    "efficiency",
    "coolant_flow",
)
SEVERITY_BANDS = (("low", 0.0, 0.4), ("mid", 0.4, 0.7), ("high", 0.7, 1.0001))

_DIRECTION_CONSISTENCY_THRESHOLD = 0.7
_NOISE_CONSISTENCY_THRESHOLD = 0.5
_RELATIVE_CHANGE_EPSILON = 0.01
# Below this many contributing runs, a "coherent" direction can be pure
# chance (e.g. two runs' load cycles happening to drift the same way over
# the fault window) rather than a real, fault-driven effect. A "blocking"
# verdict should never rest on that little evidence, so it is downgraded to
# "concerning" — still surfaced, but not treated as proof of a defect.
_MIN_RUNS_FOR_BLOCKING_VERDICT = 5
# The zero-expected-direction check runs across every (class, measurement)
# pair a fault class is *not* supposed to touch — an exploratory search
# with no multiple-comparison correction, so its bar for "blocking" is
# deliberately higher than the single-hypothesis directional checks above:
# at n=16 (the pilot's per-class run count), requiring both n>=10 and
# >=85% agreement keeps the chance of a fair-coin pattern crossing the bar
# under ~1% (a two-sided binomial tail), rather than the ~8% a bare 70%/16
# bar would allow.
_STRONG_COHERENCE_THRESHOLD = 0.85
_MIN_RUNS_FOR_STRONG_COHERENCE = 10


@dataclass(frozen=True)
class ExpectedSignature:
    measurement: str
    expected_direction: int  # +1 increase, -1 decrease, 0 = expect no coherent shift
    hard: bool


_EXPECTED_SIGNATURES: dict[str, tuple[ExpectedSignature, ...]] = {
    "cooling_degradation": (
        ExpectedSignature("stack_temperature", 1, hard=True),
        ExpectedSignature("stack_pressure", -1, hard=False),
        ExpectedSignature("coolant_flow", 1, hard=False),
        ExpectedSignature("efficiency", -1, hard=False),
    ),
    "hydrogen_supply_issue": (
        ExpectedSignature("fuel_flow", -1, hard=True),
        ExpectedSignature("current", -1, hard=True),
        ExpectedSignature("voltage", -1, hard=True),
        ExpectedSignature("power_output", -1, hard=False),
    ),
    "sensor_anomaly": (
        ExpectedSignature("stack_temperature", 1, hard=True),
        ExpectedSignature("stack_pressure", 0, hard=True),
        ExpectedSignature("current", 0, hard=True),
        ExpectedSignature("voltage", 0, hard=True),
        ExpectedSignature("fuel_flow", 0, hard=True),
        ExpectedSignature("coolant_flow", 0, hard=False),
        ExpectedSignature("power_output", 0, hard=False),
        ExpectedSignature("efficiency", 0, hard=False),
    ),
}

TelemetryIndex = dict[tuple[str, str, str], list[tuple[float, float]]]


def index_telemetry(records: DatasetRecords) -> TelemetryIndex:
    """Group telemetry values by `(run_id, asset_id, measurement_type)`,
    sorted by time."""
    index: TelemetryIndex = defaultdict(list)
    for row in records.telemetry:
        key = (row["simulation_run_id"], row["asset_id"], row["measurement_type"])
        index[key].append((row["elapsed_sim_seconds"], row["value"]))
    for series in index.values():
        series.sort(key=lambda pair: pair[0])
    return index


def pre_fault_window_start(fault_start: float, fault_duration: float) -> float:
    """Start of the "pre-fault" comparison window: as long as the fault
    window itself, ending exactly at `fault_start`.

    Comparing against the *entire* run history before `fault_start` would
    dilute the baseline with the run's early load-ramp startup transient —
    worse for early-`fault_start` runs (the transient dominates the whole
    "pre" sample) than late ones (where "pre" is mostly already-settled
    behavior), making the resulting `change` depend on when in the run the
    fault happens to start rather than on the fault itself. Matching the
    lookback to `fault_duration` keeps every run's "pre" sample count
    comparable to its own "active" sample count and anchored immediately
    next to the fault boundary.
    """
    return max(0.0, fault_start - fault_duration)


def _pre_active_medians(
    series: list[tuple[float, float]],
    pre_start: float,
    fault_start: float,
    fault_end: float,
) -> tuple[float, float] | None:
    pre = [value for elapsed, value in series if pre_start <= elapsed < fault_start]
    active = [value for elapsed, value in series if fault_start <= elapsed < fault_end]
    if not pre or not active:
        return None
    return statistics.median(pre), statistics.median(active)


def _class_measurement_effect(
    runs: list[dict[str, Any]],
    measurement: str,
    telemetry_index: TelemetryIndex,
) -> dict[str, Any] | None:
    per_run: list[dict[str, Any]] = []
    for row in runs:
        run_id = row["simulation_run_id"]
        target_asset = row["target_asset_id"]
        fault_start = row["fault_start_sim_seconds"]
        fault_duration = row["fault_duration_sim_seconds"]
        if fault_start is None or fault_duration is None:
            continue
        fault_end = fault_start + fault_duration
        pre_start = pre_fault_window_start(fault_start, fault_duration)
        series = telemetry_index.get((run_id, target_asset, measurement), [])
        medians = _pre_active_medians(series, pre_start, fault_start, fault_end)
        if medians is None:
            continue
        median_pre, median_active = medians
        per_run.append(
            {
                "run_id": run_id,
                "median_pre": median_pre,
                "median_active": median_active,
                "change": median_active - median_pre,
                "severity": row["fault_severity"],
            }
        )

    if not per_run:
        return None

    overall_median_pre = statistics.median(r["median_pre"] for r in per_run)
    epsilon = max(1e-6, _RELATIVE_CHANGE_EPSILON * abs(overall_median_pre))
    directions = [
        1 if r["change"] > epsilon else (-1 if r["change"] < -epsilon else 0)
        for r in per_run
    ]
    nonzero = [d for d in directions if d != 0]
    if nonzero:
        positive_count = sum(1 for d in nonzero if d == 1)
        negative_count = sum(1 for d in nonzero if d == -1)
        majority = 1 if positive_count >= negative_count else -1
        consistency = sum(1 for d in directions if d == majority) / len(directions)
    else:
        majority = 0
        consistency = 0.0

    band_changes: dict[str, list[float]] = defaultdict(list)
    for r in per_run:
        for band_name, low, high in SEVERITY_BANDS:
            if low <= r["severity"] < high:
                band_changes[band_name].append(r["change"])
                break

    return {
        "n_runs": len(per_run),
        "median_pre": overall_median_pre,
        "median_active": statistics.median(r["median_active"] for r in per_run),
        "median_change": statistics.median(r["change"] for r in per_run),
        "majority_direction": majority,
        "direction_consistency": consistency,
        "effect_by_severity_band": {
            band: statistics.median(changes) for band, changes in band_changes.items()
        },
    }


def compute_physical_summary(records: DatasetRecords) -> dict[str, Any]:
    telemetry_index = index_telemetry(records)
    runs_by_class: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in records.runs:
        runs_by_class[row["class_label"]].append(row)

    return {
        class_label: {
            measurement: _class_measurement_effect(
                runs_by_class.get(class_label, []), measurement, telemetry_index
            )
            for measurement in MEASUREMENTS
        }
        for class_label in FAULT_CLASSES
    }


def _classify(
    effect: dict[str, Any] | None, signature: ExpectedSignature
) -> tuple[str, str]:
    """Returns `(status, note)`; `status` is one of `matches`, `blocking`,
    `concerning`, `acceptable` (shorthand for "acceptable simulator
    limitation")."""
    if effect is None:
        status = "concerning" if signature.hard else "acceptable"
        return status, "no run had both pre-fault and active-fault telemetry to compare"

    observed = effect["majority_direction"]
    consistency = effect["direction_consistency"]
    n_runs = effect["n_runs"]
    low_confidence = n_runs < _MIN_RUNS_FOR_BLOCKING_VERDICT

    def _capped(status: str) -> str:
        return "concerning" if (status == "blocking" and low_confidence) else status

    if signature.expected_direction != 0:
        matches_expected = (
            observed == signature.expected_direction
            and consistency >= _DIRECTION_CONSISTENCY_THRESHOLD
        )
        if matches_expected:
            direction_word = "increase" if observed > 0 else "decrease"
            note = f"consistent {direction_word} ({consistency:.0%} of {n_runs} runs)"
            return "matches", note
        is_reversed = (
            observed == -signature.expected_direction
            and consistency >= _DIRECTION_CONSISTENCY_THRESHOLD
        )
        if is_reversed:
            status = _capped("blocking" if signature.hard else "concerning")
            note = f"reversed direction ({consistency:.0%} of {n_runs} runs agree)"
            if low_confidence:
                note += " — too few runs for a confident (blocking) verdict"
            return status, note
        status = "concerning" if signature.hard else "acceptable"
        note = (
            f"weak or inconsistent effect (consistency={consistency:.0%}, "
            f"n={n_runs})"
        )
        return status, note

    if observed == 0 or consistency <= _NOISE_CONSISTENCY_THRESHOLD:
        return "matches", "no coherent physical shift, as expected"

    # This branch runs once per (class, measurement) pair *not* expected to
    # move — an exploratory, multiple-comparison-heavy search across every
    # channel a fault class isn't supposed to touch. A middling consistency
    # (just over 50%) is unremarkable there: at n=16 runs, an honest
    # fair-coin split already lands in the 50-70% range close to half the
    # time, and finding one or two such channels across ~24 checked
    # (class, measurement) pairs is expected by chance, not evidence of a
    # defect. Only a strong, well-evidenced pattern earns "blocking".
    is_weak_evidence = (
        consistency < _STRONG_COHERENCE_THRESHOLD
        or n_runs < _MIN_RUNS_FOR_STRONG_COHERENCE
    )
    if is_weak_evidence:
        note = (
            f"mild, inconclusive coherence (consistency={consistency:.0%}, "
            f"n={n_runs}) — plausible at this sample size without a "
            "physical mechanism; not treated as blocking"
        )
        return ("concerning" if signature.hard else "acceptable"), note

    status = _capped("blocking" if signature.hard else "concerning")
    note = (
        f"unexpected coherent shift detected (consistency={consistency:.0%}, "
        f"n={n_runs})"
    )
    if low_confidence:
        note += " — too few runs for a confident (blocking) verdict"
    return status, note


def check_physical(
    records: DatasetRecords,
) -> tuple[list[Finding], dict[str, Any], dict[str, dict[str, dict[str, str]]]]:
    """Returns `(findings, class_effects, signature_results)`."""
    class_effects = compute_physical_summary(records)
    findings: list[Finding] = []
    signature_results: dict[str, dict[str, dict[str, str]]] = {}

    for class_label, signatures in _EXPECTED_SIGNATURES.items():
        signature_results[class_label] = {}
        for signature in signatures:
            effect = class_effects[class_label].get(signature.measurement)
            status, note = _classify(effect, signature)
            signature_results[class_label][signature.measurement] = {
                "status": status,
                "note": note,
            }
            if status in ("blocking", "concerning"):
                severity: Severity = "blocking" if status == "blocking" else "medium"
                findings.append(
                    Finding(
                        severity,
                        "physical",
                        f"{class_label}: {signature.measurement} signature "
                        f"{status} — {note}",
                        evidence={"effect": effect} if effect is not None else {},
                    )
                )

    return findings, class_effects, signature_results
