import type { TimelineEventResponse, TimelineEventType } from '../types/monitoring'
import { getTimelineEventRunId } from '../utils/timelineEvent'

interface TimelineProps {
  events: TimelineEventResponse[]
  loading: boolean
  error?: string
  onRetry?: () => void | Promise<void>
  selectedEventId?: string
  onSelectEvent?: (event: TimelineEventResponse) => void
}

const EVENT_ICONS: Record<TimelineEventType, string> = {
  observation_received: '◎',
  reasoning_started: '▶',
  reasoning_completed: '✓',
  recommendation_updated: '↻',
  notification_created: '!',
  trend_changed: '⇅',
  health_changed: '♥',
  risk_changed: '⚠',
  investigation_transition: '●',
  ai_fault_alert_received: '◈',
  ai_fault_corroboration_completed: '⚗',
  ai_fault_investigation_updated: '↻',
  ai_fault_recommendation_recorded: '✚',
  ai_fault_alert_cleared: '✓',
}

export function Timeline({
  events,
  loading,
  error,
  onRetry,
  selectedEventId,
  onSelectEvent,
}: TimelineProps) {
  const newestEventId =
    events.length > 0 ? events[events.length - 1].id : undefined

  return (
    <section className="flex min-h-0 flex-1 flex-col rounded border border-slate-800 bg-slate-900/40 p-4">
      <div className="flex items-center justify-between gap-2">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-300">
          Timeline
        </h2>
      </div>
      {error && (
        <div className="mt-2 flex items-start justify-between gap-2">
          <p className="text-xs text-amber-400">{error}</p>
          {onRetry && (
            <button
              type="button"
              className="rounded border border-slate-700 px-2 py-0.5 text-[10px] text-slate-300 transition-colors hover:border-slate-500 disabled:cursor-not-allowed disabled:opacity-50"
              onClick={() => void onRetry()}
              disabled={loading}
            >
              Retry
            </button>
          )}
        </div>
      )}
      <div className="mt-3 min-h-0 flex-1 overflow-y-auto rounded border border-slate-800 bg-slate-950/60">
        {events.length > 0 ? (
          <ul className="divide-y divide-slate-800 text-xs">
            {events.map((event) => {
              const isSelected = selectedEventId
                ? event.id === selectedEventId
                : event.id === newestEventId
              const runId = getTimelineEventRunId(event)
              const isSelectable = Boolean(runId) && Boolean(onSelectEvent)
              const row = (
                <div className="flex items-start gap-3 px-3 py-2">
                  <span
                    className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-slate-800 text-[10px] text-slate-300"
                    aria-hidden="true"
                  >
                    {EVENT_ICONS[event.event_type]}
                  </span>
                  <div className="min-w-0 flex-1 space-y-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span
                        className={`text-[11px] ${
                          isSelected
                            ? 'font-semibold text-slate-50'
                            : 'font-medium text-slate-100'
                        }`}
                      >
                        {event.title}
                      </span>
                      <span className="text-[10px] text-slate-500">
                        {new Date(event.timestamp).toLocaleString()}
                      </span>
                    </div>
                    <p className="text-[11px] text-slate-400">
                      {event.description}
                    </p>
                  </div>
                </div>
              )
              return (
                <li
                  key={event.id}
                  className={
                    isSelected
                      ? 'border-l-2 border-l-slate-400'
                      : 'border-l-2 border-transparent'
                  }
                >
                  {isSelectable ? (
                    <button
                      type="button"
                      onClick={() => onSelectEvent?.(event)}
                      className="w-full text-left transition-colors hover:bg-slate-900/60"
                    >
                      {row}
                    </button>
                  ) : (
                    row
                  )}
                </li>
              )
            })}
          </ul>
        ) : !error && loading ? (
          <div className="flex h-full items-center justify-center px-3 py-6">
            <p className="text-xs text-slate-500">Loading timeline…</p>
          </div>
        ) : (
          !error && (
            <p className="px-3 py-2 text-xs text-slate-500">
              No operational events recorded for this asset yet.
            </p>
          )
        )}
      </div>
    </section>
  )
}
