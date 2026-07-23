import type { TimelineEventResponse } from '../types/monitoring'

export function getTimelineEventRunId(
  event: TimelineEventResponse,
): string | undefined {
  const runId = event.metadata.run_id
  return typeof runId === 'string' ? runId : undefined
}

/**
 * `ai_fault_*` events (reasoning_bridge_service.py) never carry a `run_id`
 * - they belong to the AI-fault path, not the core deterministic reasoning
 * pipeline, and fabricating a reasoning-run relationship for them would be
 * architecturally wrong. They do carry `investigation_id`, which resolves
 * via GET /monitoring/fault-investigations/{investigation_id} (already used
 * by ActiveFaultInvestigationCard/FaultInvestigationHistoryPanel) to real,
 * structured detail - a parallel, equally valid anchor for Event Context.
 */
export function getTimelineEventInvestigationId(
  event: TimelineEventResponse,
): string | undefined {
  const investigationId = event.metadata.investigation_id
  return typeof investigationId === 'string' ? investigationId : undefined
}
