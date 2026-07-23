#!/usr/bin/env bash
# ODIS demo environment acceptance validation.
#
# Quick acceptance (default):
#   ./scripts/validate_demo_environment.sh
#
# Presentation walkthrough from clean volumes:
#   docker compose down -v
#   docker compose -f docker-compose.yml -f docker-compose.dev.yml --profile demo up --build -d
#   ./scripts/validate_demo_environment.sh --walkthrough
set -euo pipefail

API_BASE_URL="${SIMULATOR_API_BASE_URL:-http://localhost:8000}"
BROKER_URL="${SIMULATOR_MQTT_BROKER_URL:-mqtt://localhost:1883}"
SITE_ID="${SIMULATOR_SITE_ID:-plant-alpha}"
TARGET_ASSET="${DEMO_TARGET_ASSET:-fuel-cell-stack-01}"
MAX_PENDING="${DEMO_MAX_PENDING_JOBS:-25}"
TWIN_TIMEOUT_SECONDS="${DEMO_TWIN_TIMEOUT_SECONDS:-30}"
# `demo_presentation` targets ~6:40 total (baseline ~30s, cooling_degradation
# ~30s-2:30, recovery ~2:30-6:40) — see backend/simulator/scenario_script.py.
FAULT_CHECK_START_SECONDS="${DEMO_FAULT_CHECK_START_SECONDS:-130}"
RECOVERY_MARKER_SECONDS="${DEMO_RECOVERY_MARKER_SECONDS:-370}"
WALKTHROUGH_DEADLINE_SECONDS="${DEMO_WALKTHROUGH_DEADLINE_SECONDS:-450}"
WALKTHROUGH=0
FAILED=0

PLANT_ALPHA_ASSETS=(
  "fuel-cell-stack-01"
  "fuel-cell-stack-02"
  "fuel-cell-stack-03"
  "fuel-cell-stack-04"
)

warn() {
  echo "WARN: $*"
}

fail() {
  echo "FAIL: $*"
  FAILED=1
}

metric_value() {
  local name="$1"
  local body
  # Read the full response before handing it to awk: piping curl straight
  # into `awk '... {exit}'` lets awk close its end of the pipe as soon as
  # it finds a match, which can SIGPIPE curl mid-write (exit 23) once
  # /metrics grows large enough for that race to matter — not a real
  # failure, but set -e treated it as one and killed the whole script.
  body="$(curl -fsS "${API_BASE_URL}/metrics")" || return 1
  awk -v name="${name}" '$1 == name {print $2; exit}' <<<"${body}"
}

py_asset_ids() {
  ASSETS_JSON="${1}" python3 -c '
import json
import os
import sys

assets = json.loads(os.environ["ASSETS_JSON"])
print(" ".join(item["id"] for item in assets))
'
}

py_observation_count() {
  API_BASE_URL="${API_BASE_URL}" python3 -c '
import json
import os
import urllib.request

api = os.environ["API_BASE_URL"].rstrip("/")
with urllib.request.urlopen(f"{api}/observations", timeout=15) as resp:
    data = json.load(resp)
print(len(data))
'
}

py_print_twin_report() {
  TWIN_PATH="${1}" TWIN_STATUS="${2}" TWIN_LATENCY_MS="${3}" python3 -c '
import json
import os

path = os.environ["TWIN_PATH"]
status = os.environ["TWIN_STATUS"]
latency = os.environ["TWIN_LATENCY_MS"]
twin = json.load(open(path))
state = twin["operational_state"]
rec = twin["recommendation"]
notif = twin.get("notification")
print(f"digital_twin_status={status}")
print(f"digital_twin_latency_ms={latency}")
print("health_status=" + state["health_status"])
print("health_score=" + str(state["health_score"]))
print("risk_level=" + state["risk_level"])
print("recommendation_category=" + rec["category"])
print("recommendation_priority=" + rec["priority"])
print("notification_present=" + ("yes" if notif else "no"))
if notif:
    print("notification_severity=" + notif["severity"])
print("timeline_preview_length=" + str(len(twin.get("timeline_preview", []))))
'
}

py_plant_alpha_count() {
  ASSETS_JSON="${1}" python3 -c '
import json
import os

assets = json.loads(os.environ["ASSETS_JSON"])
expected = {
    "fuel-cell-stack-01",
    "fuel-cell-stack-02",
    "fuel-cell-stack-03",
    "fuel-cell-stack-04",
}
present = {item["id"] for item in assets}
print(len(expected & present))
'
}

py_seconds_to_ms() {
  TWIN_SECONDS="${1}" python3 -c '
import os
print(int(float(os.environ["TWIN_SECONDS"]) * 1000))
'
}

py_fault_investigation_report() {
  FAULT_JSON="${1}" python3 -c '
import json
import os

raw = os.environ["FAULT_JSON"]
data = json.loads(raw) if raw else {}
active = data.get("active_investigation")
print("ai_fault_active=" + ("yes" if active else "no"))
if active:
    print("ai_fault_diagnosed_class=" + str(active.get("diagnosed_fault_class", "")))
    print("ai_fault_corroboration_result=" + str(active.get("corroboration_result", "")))
    print("ai_fault_investigation_status=" + str(active.get("investigation_status", "")))
    missing = [
        field
        for field in ("authority_boundary_note", "corroboration_result", "diagnosed_fault_class")
        if not active.get(field)
    ]
    print("ai_fault_missing_fields=" + (",".join(missing) if missing else "none"))
'
}

py_latest_temperature() {
  TELEMETRY_JSON="${1}" python3 -c '
import json
import os

raw = os.environ.get("TELEMETRY_JSON", "")
if not raw:
    print("")
    raise SystemExit(0)
data = json.loads(raw)
samples = data[0]["samples"] if data else []
print(samples[-1]["value"] if samples else "")
'
}

py_temp_risen() {
  BASELINE_TEMP="${1}" TEMP_NOW="${2}" python3 -c '
import os
baseline = float(os.environ["BASELINE_TEMP"])
current = float(os.environ["TEMP_NOW"])
print(1 if current > baseline + 0.5 else 0)
'
}

py_walkthrough_report() {
  WALK_START="${1}" \
  WALK_ASSETS="${2}" \
  WALK_TWIN="${3}" \
  WALK_REASONING="${4}" \
  WALK_FAULT="${5}" \
  WALK_MAX_PENDING="${6}" \
  WALK_RECOVERY="${7}" \
  WALK_LATENCY_FILE="${8}" \
  WALK_AI_FAULT="${9}" \
  python3 -c '
import os

start = float(os.environ["WALK_START"])

def fmt(raw: str) -> str:
    value = float(raw)
    return "n/a" if value <= 0 else f"{value - start:.1f}s"

assets = os.environ["WALK_ASSETS"]
twin = os.environ["WALK_TWIN"]
reasoning = os.environ["WALK_REASONING"]
fault = os.environ["WALK_FAULT"]
max_pending = os.environ["WALK_MAX_PENDING"]
recovery = os.environ["WALK_RECOVERY"]
latency_file = os.environ["WALK_LATENCY_FILE"]
ai_fault = os.environ["WALK_AI_FAULT"]

latencies = []
try:
    with open(latency_file) as handle:
        latencies = [float(line.strip()) for line in handle if line.strip()]
except FileNotFoundError:
    pass

print("--- walkthrough timeline ---")
print(f"time_until_four_assets={fmt(assets)}")
print(f"time_until_digital_twin={fmt(twin)}")
print(f"time_until_baseline_reasoning={fmt(reasoning)}")
print(f"time_until_fault_transition={fmt(fault)}")
print(f"time_until_ai_fault_investigation={fmt(ai_fault)}")
print(f"max_pending_queue_depth={max_pending}")
if latencies:
    latencies.sort()
    p50 = latencies[len(latencies) // 2]
    p95 = latencies[max(0, int(len(latencies) * 0.95) - 1)]
    print(f"digital_twin_latency_p50_ms={p50:.0f}")
    print(f"digital_twin_latency_p95_ms={p95:.0f}")
else:
    print("digital_twin_latency_p50_ms=n/a")
    print("digital_twin_latency_p95_ms=n/a")
print(f"time_until_recovery_outcome={fmt(recovery)}")
'
}

main() {
while [[ $# -gt 0 ]]; do
  case "$1" in
    --walkthrough)
      WALKTHROUGH=1
      shift
      ;;
    *)
      echo "unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

echo "=== ODIS demo environment validation (MQTT required) ==="
echo "api=${API_BASE_URL} broker=${BROKER_URL} site=${SITE_ID}"
echo "mode=$([[ ${WALKTHROUGH} -eq 1 ]] && echo walkthrough || echo acceptance)"
echo

# --- Diagnostic checks (informational; do not fail acceptance alone) ---
echo "--- diagnostics ---"
if curl -fsS "${API_BASE_URL}/health" >/dev/null; then
  echo "api_health=ok"
else
  warn "API /health unreachable"
fi

if curl -fsS "${API_BASE_URL}/live" >/dev/null; then
  echo "api_live=ok"
else
  warn "API /live unreachable"
fi

if ! command -v mosquitto_sub >/dev/null 2>&1; then
  warn "mosquitto_sub not installed; skipping live MQTT subscription check"
elif timeout 5 mosquitto_sub \
  -h "${BROKER_URL#mqtt://}" \
  -t "odis/v1/${SITE_ID}/+/telemetry/+" \
  -C 1 -W 5 >/dev/null 2>&1; then
  echo "mqtt_telemetry=received"
else
  warn "no MQTT telemetry observed within 5s (broker may still be starting)"
fi
echo

# --- Required acceptance checks ---
echo "--- required acceptance ---"

assets_json="$(curl -fsS "${API_BASE_URL}/monitoring/assets" 2>/dev/null || true)"
if [[ -z "${assets_json}" ]]; then
  fail "unable to list monitoring assets"
  assets_json="[]"
fi

asset_ids="$(py_asset_ids "${assets_json}")"

echo "assets=${assets_json}"

for bench_id in ${asset_ids:-}; do
  if [[ "${bench_id}" == *bench* ]]; then
    fail "benchmark asset ${bench_id} present — reset volumes before demo acceptance (docker compose down -v)"
  fi
done

present_count=0
for expected in "${PLANT_ALPHA_ASSETS[@]}"; do
  if [[ " ${asset_ids} " == *" ${expected} "* ]]; then
    present_count=$((present_count + 1))
  fi
done

if [[ "${present_count}" -ne 4 ]]; then
  fail "expected exactly 4 Plant Alpha assets on a clean run, found ${present_count}"
else
  echo "plant_alpha_assets=4"
fi

if ! observation_count="$(metric_value observations_created_total)"; then
  observation_count=0
fi
if awk "BEGIN {exit !(${observation_count:-0} <= 0)}"; then
  if ! observation_count="$(py_observation_count 2>/dev/null)"; then
    observation_count=0
  fi
fi

echo "observation_rows=${observation_count}"
if awk "BEGIN {exit !(${observation_count:-0} <= 0)}"; then
  fail "no telemetry observations stored"
fi

pending_count="$(metric_value reasoning_jobs_pending)"
echo "reasoning_jobs_pending=${pending_count:-unknown}"
if [[ -n "${pending_count}" ]] && awk "BEGIN {exit !(${pending_count} > ${MAX_PENDING})}"; then
  fail "reasoning queue above threshold (${MAX_PENDING})"
fi

twin_tmp="$(mktemp)"
twin_start_ms="$(python3 -c 'import time; print(int(time.time()*1000))')"
twin_http_code="$(
  curl -sS -o "${twin_tmp}" -w "%{http_code}" \
    --max-time "${TWIN_TIMEOUT_SECONDS}" \
    "${API_BASE_URL}/monitoring/assets/${TARGET_ASSET}/digital-twin" || true
)"
twin_end_ms="$(python3 -c 'import time; print(int(time.time()*1000))')"
twin_latency_ms="$((twin_end_ms - twin_start_ms))"

completed_jobs="$(metric_value reasoning_jobs_completed_total)"
if [[ -z "${completed_jobs}" ]] || awk "BEGIN {exit !(${completed_jobs:-0} <= 0)}"; then
  if [[ "${twin_http_code}" == "200" ]]; then
    latest_run_id="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("latest_reasoning_run_id",""))' "${twin_tmp}" 2>/dev/null || true)"
    if [[ -n "${latest_run_id}" ]]; then
      completed_jobs="verified_via_digital_twin"
    fi
  fi
fi
echo "reasoning_jobs_completed_total=${completed_jobs:-0}"
if [[ -z "${completed_jobs}" ]] || { [[ "${completed_jobs}" != "verified_via_digital_twin" ]] && awk "BEGIN {exit !(${completed_jobs:-0} <= 0)}"; }; then
  fail "no completed reasoning run"
fi

if [[ "${twin_http_code}" != "200" ]]; then
  fail "digital twin request failed (status=${twin_http_code}, latency_ms=${twin_latency_ms})"
  rm -f "${twin_tmp}"
else
  py_print_twin_report "${twin_tmp}" "${twin_http_code}" "${twin_latency_ms}"
  rm -f "${twin_tmp}"
fi

# AI fault-alert pipeline (v1.1): the endpoint must respond correctly even
# before any fault has fired (active_investigation=null is a normal state,
# not a failure) — this proves the fault-inference worker, reasoning
# bridge, and API wiring are intact without requiring the full scenario
# timeline to have run yet.
fault_investigation_json="$(
  curl -sS --max-time "${TWIN_TIMEOUT_SECONDS}" \
    "${API_BASE_URL}/monitoring/assets/${TARGET_ASSET}/fault-investigation" 2>/dev/null || true
)"
if [[ -z "${fault_investigation_json}" ]]; then
  fail "AI fault-investigation endpoint unreachable for ${TARGET_ASSET}"
else
  py_fault_investigation_report "${fault_investigation_json}"
fi

if [[ "${WALKTHROUGH}" -eq 1 ]]; then
  echo
  echo "--- walkthrough monitor (presentation mode, up to ${WALKTHROUGH_DEADLINE_SECONDS}s) ---"
  walkthrough_start="$(date +%s)"
  assets_ready=0
  twin_ready=0
  reasoning_ready=0
  fault_ready=0
  ai_fault_ready=0
  recovery_ready=0
  max_pending_seen=0
  baseline_health_score=""
  baseline_temperature=""
  baseline_primary_driver=""
  max_temperature_seen=""
  latency_file="$(mktemp)"
  queue_growth_fail=0
  prev_pending=""

  deadline=$((walkthrough_start + WALKTHROUGH_DEADLINE_SECONDS))
  while [[ "$(date +%s)" -lt "${deadline}" ]]; do
    now="$(date +%s)"
    elapsed=$((now - walkthrough_start))

    if [[ "${assets_ready}" -eq 0 ]]; then
      current_assets="$(curl -fsS "${API_BASE_URL}/monitoring/assets" 2>/dev/null || echo '[]')"
      count="$(py_plant_alpha_count "${current_assets}")"
      if [[ "${count}" -eq 4 ]]; then
        assets_ready="${now}"
        echo "event=four_assets_ready elapsed=${elapsed}s"
      fi
    fi

    twin_code="$(
      curl -sS -o /dev/null -w "%{http_code} %{time_total}" \
        --max-time "${TWIN_TIMEOUT_SECONDS}" \
        "${API_BASE_URL}/monitoring/assets/${TARGET_ASSET}/digital-twin" 2>/dev/null || echo "000 0"
    )"
    twin_status="${twin_code%% *}"
    twin_seconds="${twin_code##* }"
    if [[ "${twin_status}" == "200" ]]; then
      twin_latency_ms="$(py_seconds_to_ms "${twin_seconds}")"
      echo "${twin_latency_ms}" >>"${latency_file}"
      if [[ "${twin_ready}" -eq 0 ]]; then
        twin_ready="${now}"
        echo "event=digital_twin_ready elapsed=${elapsed}s latency_ms=${twin_latency_ms}"
      fi
      if [[ -z "${baseline_health_score}" ]]; then
        twin_json="$(
          curl -fsS --max-time "${TWIN_TIMEOUT_SECONDS}" \
            "${API_BASE_URL}/monitoring/assets/${TARGET_ASSET}/digital-twin" 2>/dev/null || true
        )"
        if [[ -n "${twin_json}" ]]; then
          baseline_health_score="$(
            TWIN_JSON="${twin_json}" python3 -c 'import json,os; print(json.loads(os.environ["TWIN_JSON"])["operational_state"]["health_score"])' 2>/dev/null || true
          )"
          baseline_primary_driver="$(
            TWIN_JSON="${twin_json}" python3 -c 'import json,os; print(json.loads(os.environ["TWIN_JSON"])["operational_state"]["primary_driver"])' 2>/dev/null || true
          )"
        fi
      fi
    fi

    if [[ "${elapsed}" -ge 60 && -z "${baseline_temperature}" ]]; then
      telemetry_json="$(
        curl -fsS --max-time 30 \
          "${API_BASE_URL}/monitoring/assets/${TARGET_ASSET}/telemetry?measurement_type=stack_temperature&limit=5" 2>/dev/null || true
      )"
      baseline_temperature="$(py_latest_temperature "${telemetry_json}" || true)"
    fi

    completed_now="$(metric_value reasoning_jobs_completed_total)"
    if [[ "${reasoning_ready}" -eq 0 ]]; then
      twin_run_id="$(
        curl -fsS --max-time "${TWIN_TIMEOUT_SECONDS}" \
          "${API_BASE_URL}/monitoring/assets/${TARGET_ASSET}/digital-twin" 2>/dev/null |
          python3 -c 'import json,sys; print(json.load(sys.stdin).get("latest_reasoning_run_id",""))' 2>/dev/null || true
      )"
      if [[ -n "${twin_run_id}" ]] || { [[ -n "${completed_now}" ]] && ! awk "BEGIN {exit !(${completed_now} <= 0)}"; }; then
        reasoning_ready="${now}"
        echo "event=baseline_reasoning_complete elapsed=${elapsed}s completed=${completed_now:-verified_via_digital_twin}"
      fi
    fi

    pending_now="$(metric_value reasoning_jobs_pending)"
    if [[ -n "${pending_now}" ]]; then
      if awk "BEGIN {exit !(${pending_now} > ${max_pending_seen})}"; then
        max_pending_seen="${pending_now}"
      fi
      if [[ -n "${prev_pending}" ]] && awk "BEGIN {exit !(${pending_now} > ${prev_pending} + 5)}"; then
        queue_growth_fail=1
      fi
      prev_pending="${pending_now}"
    fi

    if [[ "${fault_ready}" -eq 0 && "${elapsed}" -ge ${FAULT_CHECK_START_SECONDS} ]]; then
      telemetry_json="$(
        curl -fsS --max-time 30 \
          "${API_BASE_URL}/monitoring/assets/${TARGET_ASSET}/telemetry?measurement_type=stack_temperature&limit=5" 2>/dev/null || true
      )"
      temp_now="$(py_latest_temperature "${telemetry_json}" || true)"
      if [[ -n "${temp_now}" ]]; then
        if [[ -z "${max_temperature_seen}" ]] || awk "BEGIN {exit !(${temp_now} > ${max_temperature_seen})}"; then
          max_temperature_seen="${temp_now}"
        fi
      fi
      twin_json="$(
        curl -fsS --max-time "${TWIN_TIMEOUT_SECONDS}" \
          "${API_BASE_URL}/monitoring/assets/${TARGET_ASSET}/digital-twin" 2>/dev/null || true
      )"
      health_now=""
      driver_now=""
      if [[ -n "${twin_json}" ]]; then
        health_now="$(
          TWIN_JSON="${twin_json}" python3 -c 'import json,os; print(json.loads(os.environ["TWIN_JSON"])["operational_state"]["health_score"])' 2>/dev/null || true
        )"
        driver_now="$(
          TWIN_JSON="${twin_json}" python3 -c 'import json,os; print(json.loads(os.environ["TWIN_JSON"])["operational_state"]["primary_driver"])' 2>/dev/null || true
        )"
      fi
      temp_risen=0
      if [[ -n "${baseline_temperature}" && -n "${temp_now}" ]]; then
        temp_risen="$(py_temp_risen "${baseline_temperature}" "${temp_now}")"
      fi
      if [[ -n "${baseline_temperature}" && -n "${max_temperature_seen}" ]]; then
        temp_risen_max="$(py_temp_risen "${baseline_temperature}" "${max_temperature_seen}")"
        if [[ "${temp_risen_max}" -eq 1 ]]; then
          temp_risen=1
        fi
      fi
      health_changed=0
      if [[ -n "${baseline_health_score}" && -n "${health_now}" && "${health_now}" != "${baseline_health_score}" ]]; then
        health_changed=1
      fi
      driver_changed=0
      if [[ -n "${baseline_primary_driver}" && -n "${driver_now}" && "${driver_now}" != "${baseline_primary_driver}" ]]; then
        driver_changed=1
      fi
      if [[ "${temp_risen}" -eq 1 || "${health_changed}" -eq 1 || "${driver_changed}" -eq 1 ]]; then
        fault_ready="${now}"
        echo "event=fault_transition_verified elapsed=${elapsed}s temp=${temp_now} health=${health_now} driver_changed=${driver_changed}"
      fi
    fi

    if [[ "${ai_fault_ready}" -eq 0 && "${elapsed}" -ge ${FAULT_CHECK_START_SECONDS} ]]; then
      ai_fault_json="$(
        curl -sS --max-time "${TWIN_TIMEOUT_SECONDS}" \
          "${API_BASE_URL}/monitoring/assets/${TARGET_ASSET}/fault-investigation" 2>/dev/null || true
      )"
      ai_fault_class="$(
        AI_FAULT_JSON="${ai_fault_json}" python3 -c '
import json, os
raw = os.environ.get("AI_FAULT_JSON", "")
data = json.loads(raw) if raw else {}
active = data.get("active_investigation")
print(active.get("diagnosed_fault_class", "") if active else "")
' 2>/dev/null || true
      )"
      if [[ -n "${ai_fault_class}" ]]; then
        ai_fault_ready="${now}"
        echo "event=ai_fault_investigation_confirmed elapsed=${elapsed}s diagnosed_class=${ai_fault_class}"
      fi
    fi

    if [[ "${recovery_ready}" -eq 0 && "${elapsed}" -ge ${RECOVERY_MARKER_SECONDS} ]]; then
      recovery_ready="${now}"
      echo "event=recovery_window_reached elapsed=${elapsed}s"
    fi

    sleep 5
  done

  if [[ "${queue_growth_fail}" -eq 1 ]]; then
    fail "reasoning queue grew monotonically during walkthrough"
  fi

  if [[ "${fault_ready}" -eq 0 ]]; then
    fail "fault scenario did not produce a verified transition during walkthrough"
  fi

  if [[ "${ai_fault_ready}" -eq 0 ]]; then
    fail "AI fault-inference pipeline did not produce a confirmed investigation during walkthrough (check demo-plant SIMULATOR_TRANSPORT=kafka+http, fault-inference-worker, reasoning-bridge-worker)"
  fi

  py_walkthrough_report \
    "${walkthrough_start}" \
    "${assets_ready}" \
    "${twin_ready}" \
    "${reasoning_ready}" \
    "${fault_ready}" \
    "${max_pending_seen}" \
    "${recovery_ready}" \
    "${latency_file}" \
    "${ai_fault_ready}"
  rm -f "${latency_file}"
fi

echo
if [[ "${FAILED}" -ne 0 ]]; then
  echo "Demo environment validation FAILED."
  exit 1
fi

echo "Demo environment validation PASSED."
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  main "$@"
fi
