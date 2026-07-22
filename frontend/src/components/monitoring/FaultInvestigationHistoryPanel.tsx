import type { FaultInvestigationSummaryResponse } from '../../types/monitoring'
import { corroborationResultVariant, semanticBadgeClass } from '../../utils/statusBadges'

interface FaultInvestigationHistoryPanelProps {
  history: FaultInvestigationSummaryResponse[]
  loading: boolean
  error?: string
  onRetry: () => void
}

function readableLabel(value: string): string {
  return value.replace(/_/g, ' ')
}

export function FaultInvestigationHistoryPanel({
  history,
  loading,
  error,
  onRetry,
}: FaultInvestigationHistoryPanelProps) {
  return (
    <section
      className="rounded border px-4 py-4"
      style={{ borderColor: 'var(--surface-border)', background: 'var(--surface-raised)' }}
      aria-label="AI fault investigation history"
    >
      <div className="flex items-center justify-between gap-2">
        <p
          className="text-[10px] font-semibold uppercase tracking-wide"
          style={{ color: 'var(--text-muted)' }}
        >
          AI fault investigation history
        </p>
        {error && (
          <button
            type="button"
            onClick={onRetry}
            className="rounded border px-2 py-0.5 text-[10px]"
            style={{ borderColor: 'var(--surface-border)', color: 'var(--text-secondary)' }}
          >
            Retry
          </button>
        )}
      </div>

      {error ? (
        <p className="mt-2 text-xs" style={{ color: 'var(--status-warning)' }}>
          {error}
        </p>
      ) : loading ? (
        <p className="mt-2 text-xs" style={{ color: 'var(--text-muted)' }}>
          Loading investigation history…
        </p>
      ) : history.length === 0 ? (
        <p className="mt-2 text-xs" style={{ color: 'var(--text-muted)' }}>
          No prior AI-detected fault investigations for this asset.
        </p>
      ) : (
        <ul className="mt-2 space-y-2">
          {history.map((item) => (
            <li
              key={item.investigation_id}
              className="rounded border px-3 py-2 text-xs"
              style={{ borderColor: 'var(--surface-border)' }}
            >
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-medium" style={{ color: 'var(--text-primary)' }}>
                  {readableLabel(item.diagnosed_fault_class)}
                </span>
                <span className="status-badge status-badge-normal">
                  {item.investigation_status}
                </span>
                <span
                  className={`status-badge ${semanticBadgeClass(
                    corroborationResultVariant(item.corroboration_result),
                  )}`}
                >
                  {readableLabel(item.corroboration_result)}
                </span>
              </div>
              <p className="mt-1" style={{ color: 'var(--text-muted)' }}>
                {new Date(item.observed_at).toLocaleString()}
              </p>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
