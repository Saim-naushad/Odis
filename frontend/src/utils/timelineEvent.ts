import type { TimelineEventResponse } from '../types/monitoring'

export function getTimelineEventRunId(
  event: TimelineEventResponse,
): string | undefined {
  const runId = event.metadata.run_id
  return typeof runId === 'string' ? runId : undefined
}
