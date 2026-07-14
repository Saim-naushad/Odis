import { useState, type ReactNode } from 'react'
import { Timeline } from '../Timeline'
import type {
  MonitoringRunDetailsResponse,
  TimelineEventResponse,
} from '../../types/monitoring'
import { getTimelineEventRunId } from '../../utils/timelineEvent'

interface InvestigationRailProps {
  events: TimelineEventResponse[]
  loading: boolean
  error?: string
  onRetryTimeline?: () => void | Promise<void>
  onOpenExpert: () => void
  expertDisabled: boolean
  selectedRunId?: string
  onSelectRun: (runId: string) => void
  runDetails?: MonitoringRunDetailsResponse
  runDetailsLoading: boolean
  runDetailsError?: string
  onRetryRunDetails?: () => void | Promise<void>
}

/** Newest timeline event tied to `runId`, used only when nothing has been clicked yet. */
function findDefaultEvent(
  events: TimelineEventResponse[],
  runId?: string,
): TimelineEventResponse | undefined {
  if (!runId) return undefined
  for (let i = events.length - 1; i >= 0; i -= 1) {
    if (getTimelineEventRunId(events[i]) === runId) return events[i]
  }
  return undefined
}

function RailSection({
  title,
  children,
  className = '',
}: {
  title: string
  children: ReactNode
  className?: string
}) {
  return (
    <section
      className={`rounded border ${className}`}
      style={{
        borderColor: 'var(--surface-border)',
        background: 'var(--surface-raised)',
      }}
    >
      <header
        className="border-b px-3 py-2"
        style={{ borderColor: 'var(--surface-border)' }}
      >
        <h3
          className="text-[10px] font-semibold uppercase tracking-wide"
          style={{ color: 'var(--text-secondary)' }}
        >
          {title}
        </h3>
      </header>
      <div className="p-3">{children}</div>
    </section>
  )
}

export function InvestigationRail({
  events,
  loading,
  error,
  onRetryTimeline,
  onOpenExpert,
  expertDisabled,
  selectedRunId,
  onSelectRun,
  runDetails,
  runDetailsLoading,
  runDetailsError,
  onRetryRunDetails,
}: InvestigationRailProps) {
  const [manuallySelectedEvent, setManuallySelectedEvent] = useState<
    TimelineEventResponse | undefined
  >(undefined)

  // Derived, not stored: falls back to the newest event for the currently
  // selected run whenever the operator hasn't clicked one explicitly.
  const selectedEvent = manuallySelectedEvent ?? findDefaultEvent(events, selectedRunId)
  const metadataEntries = selectedEvent
    ? Object.entries(selectedEvent.metadata).filter(([key]) => key !== 'run_id')
    : []

  function handleSelectEvent(event: TimelineEventResponse): void {
    setManuallySelectedEvent(event)
    const runId = getTimelineEventRunId(event)
    if (runId) onSelectRun(runId)
  }

  return (
    <aside
      className="flex min-w-0 flex-col gap-3 lg:sticky lg:top-4 lg:max-h-[calc(100vh-2rem)] lg:self-start lg:overflow-y-auto"
      aria-label="Investigation"
    >
      <div className="flex items-center justify-between">
        <h2
          className="text-xs font-semibold uppercase tracking-wide"
          style={{ color: 'var(--text-primary)' }}
        >
          Investigation
        </h2>
        <span className="text-[10px]" style={{ color: 'var(--text-muted)' }}>
          Correlate · Diagnose
        </span>
      </div>

      <div className="flex min-h-[220px] flex-1 flex-col overflow-hidden">
        <Timeline
          events={events}
          loading={loading}
          error={error}
          onRetry={onRetryTimeline}
          selectedEventId={selectedEvent?.id}
          onSelectEvent={handleSelectEvent}
        />
      </div>

      <RailSection title="Event context">
        {!selectedEvent && !runDetails && !runDetailsLoading && !runDetailsError ? (
          <p className="text-xs leading-relaxed" style={{ color: 'var(--text-muted)' }}>
            Select a timeline event to inspect context and correlate with telemetry.
          </p>
        ) : (
          <div className="max-h-[40vh] space-y-3 overflow-y-auto pr-1 text-xs">
            {selectedEvent && (
              <div>
                <h4
                  className="text-[10px] font-semibold uppercase tracking-wide"
                  style={{ color: 'var(--text-secondary)' }}
                >
                  Event
                </h4>
                <div className="mt-1 space-y-1">
                  <p className="font-medium" style={{ color: 'var(--text-primary)' }}>
                    {selectedEvent.title}
                  </p>
                  <p style={{ color: 'var(--text-muted)' }}>
                    {new Date(selectedEvent.timestamp).toLocaleString()}
                  </p>
                  <p style={{ color: 'var(--text-secondary)' }}>
                    {selectedEvent.description}
                  </p>
                  {metadataEntries.length > 0 && (
                    <dl className="space-y-0.5">
                      {metadataEntries.map(([key, value]) => (
                        <div key={key} className="flex justify-between gap-2">
                          <dt style={{ color: 'var(--text-muted)' }}>{key}</dt>
                          <dd
                            className="min-w-0 truncate text-right"
                            style={{ color: 'var(--text-secondary)' }}
                          >
                            {String(value)}
                          </dd>
                        </div>
                      ))}
                    </dl>
                  )}
                </div>
              </div>
            )}

            <div>
              <h4
                className="text-[10px] font-semibold uppercase tracking-wide"
                style={{ color: 'var(--text-secondary)' }}
              >
                Associated reasoning run
              </h4>
              {runDetails ? (
                <div className="mt-1 space-y-2">
                  <p style={{ color: 'var(--text-primary)' }}>
                    {runDetails.operational_situation.assessment}
                  </p>
                  <p style={{ color: 'var(--text-secondary)' }}>
                    {runDetails.decision_plan.recommendation}
                  </p>
                  <p style={{ color: 'var(--text-muted)' }}>
                    Priority: {runDetails.decision_plan.priority} ·{' '}
                    {runDetails.decision_plan.justification}
                  </p>
                  {runDetails.decision_plan.confidence && (
                    <div
                      className="rounded border p-2"
                      style={{ borderColor: 'var(--surface-border)' }}
                    >
                      <p
                        className="font-semibold"
                        style={{ color: 'var(--text-secondary)' }}
                      >
                        Confidence: {runDetails.decision_plan.confidence.value}/100
                      </p>
                      <p style={{ color: 'var(--text-muted)' }}>
                        {runDetails.decision_plan.confidence.rationale}
                      </p>
                    </div>
                  )}
                  {runDetails.decision_plan.evidence &&
                    runDetails.decision_plan.evidence.length > 0 && (
                      <div>
                        <p
                          className="font-semibold"
                          style={{ color: 'var(--text-secondary)' }}
                        >
                          Evidence
                        </p>
                        <ul className="mt-1 space-y-1">
                          {runDetails.decision_plan.evidence.map((item) => (
                            <li key={item.id} style={{ color: 'var(--text-secondary)' }}>
                              {item.description} ({item.measurement_type}:{' '}
                              {item.observed_value}, w=
                              {item.contribution_weight.toFixed(2)})
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                  {runDetails.decision_plan.alternative_hypotheses &&
                    runDetails.decision_plan.alternative_hypotheses.length > 0 && (
                      <div>
                        <p
                          className="font-semibold"
                          style={{ color: 'var(--text-secondary)' }}
                        >
                          Alternative hypotheses
                        </p>
                        <ul className="mt-1 space-y-1">
                          {runDetails.decision_plan.alternative_hypotheses.map(
                            (item) => (
                              <li
                                key={item.title}
                                style={{ color: 'var(--text-secondary)' }}
                              >
                                {item.title} ({item.confidence}%) — {item.reason}
                              </li>
                            ),
                          )}
                        </ul>
                      </div>
                    )}
                </div>
              ) : runDetailsLoading ? (
                <p className="mt-1" style={{ color: 'var(--text-muted)' }}>
                  Loading reasoning context…
                </p>
              ) : runDetailsError ? (
                <div className="mt-1 flex items-start justify-between gap-2">
                  <p className="text-amber-400">{runDetailsError}</p>
                  {onRetryRunDetails && (
                    <button
                      type="button"
                      onClick={() => void onRetryRunDetails()}
                      className="rounded border px-2 py-0.5 text-[10px] transition-colors hover:opacity-90"
                      style={{
                        borderColor: 'var(--surface-border)',
                        color: 'var(--text-secondary)',
                      }}
                    >
                      Retry
                    </button>
                  )}
                </div>
              ) : (
                <p className="mt-1" style={{ color: 'var(--text-muted)' }}>
                  No reasoning run associated with this event yet.
                </p>
              )}
            </div>
          </div>
        )}
      </RailSection>

      <RailSection title="Diagnostics">
        <p className="mb-3 text-xs leading-relaxed" style={{ color: 'var(--text-secondary)' }}>
          Review reasoning runs, evidence weights, and structured assessments for the
          selected asset.
        </p>
        <button
          type="button"
          onClick={onOpenExpert}
          disabled={expertDisabled}
          className="w-full rounded border px-3 py-2.5 text-left text-xs font-medium transition-colors hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
          style={{
            borderColor: 'var(--surface-border)',
            background: 'var(--surface-base)',
            color: 'var(--text-primary)',
          }}
        >
          Open reasoning runs &amp; diagnostics
        </button>
      </RailSection>
    </aside>
  )
}
