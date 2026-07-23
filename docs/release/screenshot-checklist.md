# v1.1 Screenshot Checklist

Screenshots to capture for the GitHub release, README, and portfolio use. All
shots come from the `demo_presentation` scenario on a clean database (see
[Demo Environment → Recording procedure](../platform/demo-environment.md#reproducible-screenshots--demo-video)
for exact startup steps and phase-change log cues). Do not generate these
images as part of this PR — this is the shot list for the next recording
session.

Capture at the existing resolution/crop used in `docs/assets/` (1024px wide
in README, full browser width in the source PNG) so new shots match the
existing set stylistically.

## Why existing screenshots need to be redone

`docs/assets/dashboard-overview.png`, `dashboard-telemetry.png`, and
`dashboard-investigation.png` were captured on 2026-07-12, before the
operator investigation lifecycle (`8b40ffb`) and dashboard demo-readiness
polish (`49af982`) landed. They currently show:

- A **"Platform degraded"** status pill in the header instead of "Platform
  healthy" — misleading for a release screenshot.
- No investigation-status badge or operator acknowledge/investigate/resolve
  controls in the Recommended Action panel — the newest headline feature
  in this release isn't visible anywhere in the current image set.
- Fleet chips for `fuel-cell-stack-02/03/04` showing raw asset IDs instead
  of resolved names, inconsistent with the resolved name shown for stack-01.

All three should be recaptured alongside the new shots below, from the same
recording session, so the whole set is internally consistent.

**Also stale as of 2026-07-23 (post fleet-state/lifecycle/timeline fixes):**
the current `docs/assets/dashboard-overview.png` and
`dashboard-investigation-lifecycle.png` (captured just before these fixes)
predate them and should be recaptured:

- `dashboard-overview.png` shows a CRITICAL "Immediate mitigation required"
  banner alongside an otherwise-NORMAL, LOW-risk fleet, with no
  explanation — exactly the contradiction fixed below. A fresh capture
  should show either no banner, or a correctly-labeled one.
- `dashboard-investigation-lifecycle.png` only reached ACKNOWLEDGED (the
  recommendation-identity bug made INVESTIGATING/RESOLVED unreliable to
  capture at the time). A fresh capture should reach at least INVESTIGATING.

## Shot list

| # | Filename | Purpose | Simulator phase | What should be visible |
|---|----------|---------|------------------|-------------------------|
| 1 | `dashboard-overview.png` | Hero shot for README and release notes — proves the platform is live and healthy | `normal_operation` (00:00–00:30, before `cooling_degradation` starts) | Header shows a green "LIVE" indicator and **no** platform-status text (the header only renders status text when the platform is *not* healthy — see `ProductHeader.tsx`'s `showPlatformSecondary`); all four fleet chips with resolved names and NORMAL status; **no CRITICAL banner** — see [Demo Environment → Notification severity now matches current health](../platform/demo-environment.md#notification-severity-now-matches-current-health-2026-07-23); if an older WARNING notification is still open, its disambiguation note must be visible, never an unexplained CRITICAL banner over an otherwise-NORMAL fleet |
| 2 | `dashboard-ai-fault-diagnosis.png` | Shows the v1.1 flagship capability — a model-detected fault corroborated by deterministic rules — which no existing screenshot covers | AI-fault (Kafka) path, ~0:55–1:05 after a clean start — well before the legacy MQTT-path CRITICAL window | AI-Assisted Fault Diagnosis card: `cooling_degradation`/`confirmed` badges, the Deterministic corroboration block (`partially_corroborated`, rule IDs), the recommendation block, and the always-visible authority-boundary sentence |
| 3 | `dashboard-cooling-alert.png` | Shows a real fault surfacing as an explainable, prioritized recommendation | Any tick where the legacy health badge reads CRITICAL — a confirmed CRITICAL health reading only; see [Demo Environment → Known limitations](../platform/demo-environment.md#known-limitations) for why this is opportunistic rather than a fixed window | Fleet chip for stack-01 in CRITICAL with a low health score; active alert banner labeled CRITICAL; Recommended Action panel with priority/urgency/category badges and numbered steps. If the badge only reaches WARNING ("Elevated risk identified"), that's now a real, distinct, correctly-labeled state — acceptable as a substitute, not a bug |
| 4 | `dashboard-investigation-lifecycle.png` | Documents the operator investigation workflow — the newest capability, not shown in any current asset | Any point where a Recommended Action exists (does not require CRITICAL — a baseline P3/"monitor" recommendation is enough); walk Acknowledge → Start investigating in order | Recommended Action panel with an investigation-status badge showing **at least INVESTIGATING** (the lifecycle is now reliable end to end — don't settle for ACKNOWLEDGED if INVESTIGATING is reachable in the same session), the "Acting as [operator]" control, the transition timestamp/actor line, and the next available action button (e.g. "Resolve") |
| 5 | `dashboard-telemetry.png` | Shows telemetry correlated with reasoning, not just a status summary | Same window as #3 | Telemetry panel with `stack_temperature` or `coolant_flow` trending adversely, time range/resolution controls visible, investigation timeline panel visible alongside it |
| 6 | `dashboard-investigation-timeline.png` | Shows the reasoning trace is real evidence, not a canned message | Any point with ≥3 timeline events, with one selected | Investigation timeline with multiple events, one selected; Event Context panel populated (not the empty "Select a timeline event…" placeholder). **Prefer a visible `ai_fault_*` event** (shows the newer AI-fault Event Context, not a reasoning run) if one is showing in the 5-event preview at capture time; a populated deterministic reasoning event (`reasoning_started`/`reasoning_completed`) is an equally acceptable fallback — the preview is capped at 5 recent events and observation events can crowd an AI-fault event out, so don't wait indefinitely for one to appear |
| 7 | `dashboard-recovery.png` | Closes the narrative loop — shows reasoning re-assessing automatically, not a manual reset | `recovery`, best-effort — see [Demo Environment → Known limitations](../platform/demo-environment.md#known-limitations); the legacy health badge is not currently guaranteed to settle into a held NORMAL. Capturing the AI investigation's `cleared` empty state is an acceptable substitute if the legacy badge doesn't cooperate. **Do not force this shot** | Health score trending back up on stack-01, holding at NORMAL; alert banner cleared or notification marked resolved; investigation status shows RESOLVED if step #4 was carried through — or, as a substitute, the AI-Assisted Fault Diagnosis card's cleared empty state |

Seven shots is the target set. If time is limited, 1–4 are the minimum viable
set — they cover baseline, the AI-assisted diagnosis path, the legacy fault
alert, and the investigation-lifecycle feature, which is also the minimum
cut described in the demo script.

## Manual capture workflow

There is no maintained capture script in this repository — a prior
Playwright-based helper (`scripts/capture_dashboard_screenshots.py`) was
removed because it targeted the pre-investigation-lifecycle dashboard: it
took the first available shot immediately (reproducing the exact
"Platform degraded" / missing-controls problem described above), used
filenames and content that no longer match the shot list (no
`dashboard-cooling-alert.png`, `dashboard-investigation-lifecycle.png`, or
`dashboard-investigation-timeline.png` support), and its Playwright
dependency was never declared in `pyproject.toml`. Reintroducing automated
capture is future work, not part of this checklist. Capture manually:

1. **States to capture** — the seven rows in the [Shot list](#shot-list)
   above; each row's "Simulator phase" and "What should be visible" columns
   are the acceptance criteria for that shot.
2. **Viewport and resolution** — use a **1440×900** browser window at **2x**
   device pixel ratio (DevTools → toggle device toolbar → set a custom
   viewport with 2x scaling, or an equivalent OS-level Retina/HiDPI
   capture). This reproduces the existing set's ~2880px-wide source PNGs,
   downscaled to 1024px wide for README embedding — keep this consistent
   across all seven shots so the set matches stylistically.
3. **Filenames** — use exactly the filenames in the Shot list table's
   `Filename` column (e.g. `dashboard-cooling-alert.png`), not generic or
   timestamped names.
4. **Where to save** — `docs/assets/`, alongside the existing
   `dashboard-incident.png`.
5. **Avoiding local/personal information** — capture from the standard
   `docker compose --profile demo up --build -d` stack on `localhost:8080`
   only; do not include browser chrome, OS menu bars, notification
   toasters, or any second monitor/desktop content in the crop. If the
   investigation-lifecycle shot (#4) requires selecting an operator, use a
   generic operator name (e.g. `operator-1`), never a real name or email.
6. **Use the current, post-AI dashboard** — every shot must come from a
   build that includes the v1.1 operator investigation lifecycle and
   AI-fault-alert path (this checklist's whole point is that the previous
   set predated both). Confirm `git log -1` on the running build includes
   `8b40ffb` (investigation lifecycle) and the AI-fault-alert commits
   before shooting.
- Use the phase-change log lines from `docker compose logs -f demo-plant` to
  know when each *scenario* phase starts, but time the CRITICAL/recovered
  shots off the actual dashboard state (or the digital-twin API) — the
  health badge lags a phase-change line by tens of seconds, per
  [Demo Environment → Verified timing](../platform/demo-environment.md#verified-timing-presentation-cadence).
- Re-run `./scripts/validate_demo_environment.sh` after capture to confirm
  the session used to shoot these screenshots also passes acceptance.
