import type { ReactNode } from 'react'
import { Timeline } from '../Timeline'
import type { TimelineEventResponse } from '../../types/monitoring'

interface InvestigationRailProps {
  events: TimelineEventResponse[]
  loading: boolean
  error?: string
  onRetryTimeline?: () => void | Promise<void>
  onOpenExpert: () => void
  expertDisabled: boolean
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
}: InvestigationRailProps) {
  return (
    <aside
      className="flex min-w-0 flex-col gap-3 lg:sticky lg:top-4 lg:max-h-[calc(100vh-2rem)] lg:self-start"
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

      <div className="min-h-[220px] flex-1 overflow-hidden">
        <Timeline
          events={events}
          loading={loading}
          error={error}
          onRetry={onRetryTimeline}
        />
      </div>

      <RailSection title="Event context">
        <p className="text-xs leading-relaxed" style={{ color: 'var(--text-muted)' }}>
          Select a timeline event to inspect context and correlate with telemetry.
        </p>
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
