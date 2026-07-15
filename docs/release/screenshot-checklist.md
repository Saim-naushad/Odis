# v1.0.0 Screenshot Checklist

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

## Shot list

| # | Filename | Purpose | Simulator phase | What should be visible |
|---|----------|---------|------------------|-------------------------|
| 1 | `dashboard-overview.png` | Hero shot for README and release notes — proves the platform is live and healthy | `normal_operation` (00:00–00:30, before `cooling_degradation` starts) | Header shows "Platform healthy" and "LIVE"; all four fleet chips with resolved names and NORMAL status; no active alert banner |
| 2 | `dashboard-cooling-alert.png` | Shows a real fault surfacing as an explainable, prioritized recommendation | CRITICAL window, **~02:50–03:23** into the script | Fleet chip for stack-01 in CRITICAL with a low health score; active alert banner; Recommended Action panel with priority/urgency/category badges and numbered steps |
| 3 | `dashboard-investigation-lifecycle.png` | Documents the operator investigation workflow — the newest capability, not shown in any current asset | Same window as #2 (CRITICAL persists into WARNING through ~06:12, so there's no rush), after clicking "Acknowledge" or "Start investigating" | Recommended Action panel with an investigation-status badge (e.g. ACKNOWLEDGED), the "Acting as [operator]" control, the transition timestamp/actor line, and the next available action button (e.g. "Resolve") |
| 4 | `dashboard-telemetry.png` | Shows telemetry correlated with reasoning, not just a status summary | Same window as #2 (**~02:50–06:12**) | Telemetry panel with `stack_temperature` or `coolant_flow` trending adversely, time range/resolution controls visible, investigation timeline panel visible alongside it |
| 5 | `dashboard-investigation-timeline.png` | Shows the reasoning trace is real evidence, not a canned message | Same window as #2–4, with a timeline event selected | Investigation timeline with multiple reasoning-run and notification events; Event Context panel populated after selecting an event (not the empty "Select a timeline event…" placeholder) |
| 6 | `dashboard-recovery.png` | Closes the narrative loop — shows reasoning re-assessing automatically, not a manual reset | `recovery`, once health has settled back to a held NORMAL, **~06:12–06:40** | Health score trending back up on stack-01, holding at NORMAL; alert banner cleared or notification marked resolved; investigation status shows RESOLVED if step #3 was carried through |

Six shots is the target set. If time is limited, 1–4 are the minimum viable
set — they cover baseline, fault, the new investigation-lifecycle feature,
and telemetry correlation, which is also the minimum cut described in the
demo script.

## Capture notes

- Use the phase-change log lines from `docker compose logs -f demo-plant` to
  know when each *scenario* phase starts, but time the CRITICAL/recovered
  shots off the actual dashboard state (or the digital-twin API) — the
  health badge lags a phase-change line by tens of seconds, per
  [Demo Environment → Verified timing](../platform/demo-environment.md#verified-timing-presentation-cadence).
- Keep browser window width consistent across all shots (the current set
  appears to be a standard 2880px-wide capture, downscaled to 1024px for
  README embedding).
- Re-run `./scripts/validate_demo_environment.sh` after capture to confirm
  the session used to shoot these screenshots also passes acceptance.
