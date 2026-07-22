# Fault investigation dashboard (PR179)

Exposes the reasoning bridge's AI-detected fault investigations
(`docs/reasoning-bridge.md`) to the operator dashboard: a read-model API,
an SSE bridge, and dashboard integration. This PR is read-model only — no
new model work, no new deterministic rules, no autonomous controls.

## Why a separate doc from `reasoning-bridge.md`

`reasoning-bridge.md` documents the backend pipeline that produces
`AiFaultEvidence` rows (PR177/178) and explicitly deferred all UI/API work
to this PR. Keeping the two docs separate matches that boundary: one
covers how a fault gets diagnosed and corroborated, this one covers how
an operator sees it.

## API read model

Three endpoints, added in `backend/app/api/routers/fault_investigations.py`
(same `/monitoring` URL prefix as the existing router, kept in a separate
file since `monitoring.py` was already large):

- `GET /monitoring/assets/{asset_id}/fault-investigation` — the asset's
  current investigation, if any. **Always 200 for a known asset** —
  `{"active_investigation": null}` when the asset has no AI-fault history
  yet, or its latest investigation is already `CLEARED`. Both are normal
  operational states, not errors. 404 only for an unknown asset id.
- `GET /monitoring/assets/{asset_id}/fault-investigations` — bounded
  (`limit`, default 20), most-recent-first history: one row per distinct
  `investigation_id` (its latest evidence row). Empty list, not 404, when
  there's no history. 404 only for an unknown asset id.
- `GET /monitoring/fault-investigations/{investigation_id}` — the full
  chronological lifecycle of one investigation (every evidence row, oldest
  first). 404 for an unknown investigation id.

### DTO tiering (`backend/app/api/schemas/fault_investigation.py`)

`FaultInvestigationSummaryResponse` mirrors the operator information
hierarchy top to bottom: fault state → corroboration → urgency →
recommendation → authority boundary note → supporting evidence →
provenance (collapsed, secondary tier in the UI).

**Never returned by any endpoint**: `class_scores` (the full per-class
model score distribution) and `evidence_items` (upstream model-internal
values — physics-residual features, probability-flavored scores). Both
stay persisted on `AiFaultEvidence` for internal diagnostics only. The
provenance tier surfaces only `model_system_version`, `model_hash`,
`policy_hash`, `feature_schema_version`, `latest_model_score`,
`score_semantics` (the fixed caveat sentence below), and `source_event_id`
— hashes/versions/score, never raw internals.

### Supporting evidence

`FaultRecommendation.supporting_observation_ids` (already populated
deterministically by `recommendation_policy.py`/`corroboration.py` from
real `Observation` rows in the alert's own asset/time-window) is resolved
via bounded, single-PK `ObservationRepository.get()` lookups
(`FAULT_INVESTIGATION_EVIDENCE_LIMIT = 8`) into compact
`{observation_id, measurement_type, value, unit, observed_at, role}`
summaries. `role` is always `"supporting"` today — the field exists so a
future corroboration policy that also surfaces conflicting/contextual
readings doesn't require an API change. This resolution only happens for
the single active/current investigation, never per-row across a history
list, to avoid an N+1 query pattern.

### History correctness

An investigation with several lifecycle rows (e.g. a `class_changed`
chain) must count once against `limit`, not once per row — otherwise a
small `limit` could silently drop an older, separate investigation.
`SqlAlchemyAiFaultEvidenceRepository.list_for_asset_grouped_by_investigation`
implements this with a `ROW_NUMBER() OVER (PARTITION BY investigation_id
ORDER BY observed_at DESC)` window query filtered to rank 1, which is
portable across SQLite (the test suite) and PostgreSQL (production) —
`DISTINCT ON` was avoided as it's Postgres-only.

No new Alembic migration was needed: the existing `ai_fault_evidence`
table already indexes `asset_id`, `source_event_id`, and
`investigation_id`.

## Score language and authority boundary

Fixed strings, defined once in `backend/app/api/schemas/fault_investigation.py`
so the frontend never hand-duplicates policy language:

- `score_semantics`: *"This is an uncalibrated diagnostic ranking score,
  not a probability or confidence level — it does not represent the
  percentage likelihood that the fault is real."* Rendered as
  `Diagnostic model score: {value.toFixed(2)}` followed by this sentence —
  never as a percentage or "chance of X" phrasing.
- `authority_boundary_note`: *"This fault was detected by a diagnostic
  model and is evidence, not a confirmed diagnosis. The recommendation
  below reflects only what deterministic telemetry rules corroborated
  against real observations — not the model's own score."* Always visible
  on the active fault card, never collapsed.

## SSE bridge

**The gap this closes**: `ReasoningBridgeService` persists evidence and
timeline rows directly in its own transaction and never touched
`OutboxEvent`/`DomainEventBus`; its worker process
(`reasoning_bridge_worker_main.py`) never called
`bootstrap_application_runtime()`. A processed fault alert produced zero
SSE signal — the dashboard would only see it on the next poll/refetch.

**The fix**, mirroring `InvestigationService.record_transition` and
`worker_main.py`'s existing pattern exactly:

1. `reasoning_bridge_worker_main.py` now calls
   `bootstrap_application_runtime(settings, unit_of_work_factory=...)` and
   passes the resulting `domain_event_bus`/`outbox_dispatcher` into
   `ReasoningBridgeService`.
2. `ReasoningBridgeService.process_alert_transition` writes one
   `OutboxEvent(event_type="AiFaultInvestigationUpdated")` row in the
   *same* transaction as the evidence + timeline writes, commits once,
   then calls `outbox_dispatcher.dispatch()` — matching this codebase's
   "one uow, one commit, dispatch after" convention. The existing
   idempotency check (duplicate alert replay) returns before any of this
   runs, so a replayed Kafka message never produces a second outbox row.
3. `OutboxDispatcher` publishes the new `AiFaultInvestigationUpdated`
   domain event onto the `DomainEventBus`; `MonitoringEventHandler`
   translates it into a minimal SSE signal.
4. `RedisMonitoringEventSource` carries that signal from the
   reasoning-bridge-worker process to the API process over Redis pub/sub —
   the same cross-process transport the reasoning worker already uses for
   `asset_updated`/`run_updated`.

**`MonitoringEvent` was deliberately not extended** with new fields.
Every existing SSE event (`asset_updated`, `run_updated`) is a minimal
invalidation signal — `type`/`timestamp`/`asset_id` only — never the full
entity. `fault_investigation_updated` follows the same shape: the browser
always refetches the durable REST read model on receipt; the SSE payload
itself is never treated as authoritative state. This event is
deliberately **not** mapped in `integration_event_mapping.py` — it never
reaches Kafka, so browser delivery never depends on Kafka connectivity
(`fault_reasoning_result.v1` remains the separate, existing Kafka
contract, published directly by the worker via `kafka_io.py`).

## Dashboard integration

- `ActiveFaultInvestigationCard` (`frontend/src/components/monitoring/`) —
  the primary surface, placed directly below `ActiveAlertBanner` and above
  `ActionPlaybook` in the main column. Renders the full hierarchy;
  provenance is a collapsed `<details>` section. Deliberately titled
  "AI-Assisted Fault Diagnosis" (not "Recommendation") to avoid confusion
  with `ActionPlaybook`'s older, unrelated OperationalState-derived
  recommendation — the two are parallel concepts, never merged.
- `FaultInvestigationHistoryPanel`, added to `ExpertDetailsDrawer`, lists
  prior investigations for the selected asset.
- `useFaultInvestigation` — a standalone hook (query keys
  `['monitoring','asset',assetId,'fault-investigation']` and
  `[...,'fault-investigation-history']`), following the same SSE-gated
  polling and initial-vs-refresh error-formatting pattern as
  `useMonitoringDashboard`.
- `monitoringEventDispatcher` gained a `fault_investigation_updated` case,
  invalidating both new query keys plus `digital-twin` (so new
  `ai_fault_*` timeline rows surface live in `InvestigationRail`/`Timeline`).
- `statusBadges.ts` gained `faultUrgencyVariant` and
  `corroborationResultVariant` — two distinct mapping functions (urgency
  is "how alarmed," corroboration is "how much agreement"), both mapped
  onto the existing 4-tier badge tokens. `corroborated` intentionally caps
  at `warn`, never `danger` — corroboration strength alone must not read
  as critical for a fault that was only ever model-detected.
- `Timeline.tsx` gained icons for the 5 `ai_fault_*` timeline event types
  already written by `ReasoningBridgeService`.

## Lifecycle and failure states

- **No active investigation**: normal empty state text, not implied
  perfect health.
- **Class changed**: the card shows the new diagnosis;
  `previous_diagnosed_fault_class` is shown inline.
- **Cleared**: the active card returns to the empty state; the cleared
  occurrence remains visible in history.
- **New post-clear occurrence**: a new `investigation_id` — shown as a new
  investigation, never a continuation.
- **Duplicate/replayed alert-transition events**: no duplicate evidence
  row, timeline entries, outbox row, or SSE event — enforced by
  `ReasoningBridgeService`'s existing idempotency check.
- **SSE disconnected**: the dashboard's existing 60s fallback poll takes
  over (via `sseConnectionState`); the last durable API state stays
  visible, never cleared solely because SSE dropped.
- **Withheld recommendation**: `recommendation.status === "withheld"` —
  the card renders "Recommendation withheld" and the backend-provided
  `reason`/`action_summary`/`limitations` text explaining why, rather than
  a hardcoded frontend string.

## Non-goals (unchanged from the reasoning bridge)

No new fault classes, model retraining, calibration, SHAP, autonomous
actions, actuator controls, MLflow, model registry, or broad dashboard
redesign. No fleet-wide (`FleetAttentionStrip`) AI-fault indicator in this
PR — deferred to a future hardening pass to avoid adding a per-asset
lookup to the fleet-summary hot path.
