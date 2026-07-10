import type { RecommendationResponse } from '../../types/monitoring'
import { priorityVariant, semanticBadgeClass } from '../../utils/statusBadges'

interface ActionPlaybookProps {
  selectedAssetId?: string
  recommendation?: RecommendationResponse
  loading: boolean
  error?: string
}

function priorityAccentColor(priority: string): string {
  const variant = priorityVariant(priority)
  switch (variant) {
    case 'danger':
      return 'var(--status-critical)'
    case 'warn':
      return 'var(--status-warning)'
    case 'info':
      return 'var(--status-info)'
    default:
      return 'var(--surface-border)'
  }
}

export function ActionPlaybook({
  selectedAssetId,
  recommendation,
  loading,
  error,
}: ActionPlaybookProps) {
  const hasRecommendation = Boolean(recommendation)

  return (
    <section
      className="rounded border px-6 py-6"
      style={{
        borderColor: hasRecommendation
          ? priorityAccentColor(recommendation!.priority)
          : 'var(--surface-border)',
        borderLeftWidth: hasRecommendation ? '4px' : undefined,
        background: 'var(--surface-raised)',
        boxShadow: hasRecommendation
          ? '0 1px 0 rgb(148 163 184 / 0.08), 0 8px 24px rgb(2 6 23 / 0.35)'
          : undefined,
      }}
      aria-label="Recommended action"
    >
      <div className="flex items-center justify-between gap-2">
        <div>
          <h2
            className="text-xs font-semibold uppercase tracking-wide"
            style={{ color: 'var(--text-secondary)' }}
          >
            Recommended action
          </h2>
          {hasRecommendation && (
            <p className="mt-1 text-[10px]" style={{ color: 'var(--text-muted)' }}>
              Operator playbook — follow steps in order
            </p>
          )}
        </div>
        {loading && !error && (
          <span
            className="text-[10px] uppercase tracking-wide"
            style={{ color: 'var(--text-muted)' }}
          >
            Refreshing…
          </span>
        )}
      </div>

      {error ? (
        <p className="mt-4 text-sm" style={{ color: 'var(--status-warning)' }}>
          {error}
        </p>
      ) : recommendation ? (
        <div className="mt-5 space-y-5">
          <div className="flex flex-wrap items-center gap-2">
            <span
              className={`status-badge ${semanticBadgeClass(priorityVariant(recommendation.priority))}`}
            >
              {recommendation.priority} · {recommendation.urgency}
            </span>
            <span className="status-badge status-badge-info">{recommendation.category}</span>
          </div>

          <div>
            <p
              className="text-lg font-semibold leading-snug"
              style={{ color: 'var(--text-primary)' }}
            >
              {recommendation.title}
            </p>
            <p
              className="mt-3 text-sm leading-relaxed"
              style={{ color: 'var(--text-secondary)' }}
            >
              {recommendation.description}
            </p>
          </div>

          <div
            className="rounded border px-4 py-4"
            style={{
              borderColor: 'var(--surface-border)',
              background: 'var(--surface-base)',
            }}
          >
            <p
              className="text-[10px] font-semibold uppercase tracking-wide"
              style={{ color: 'var(--text-muted)' }}
            >
              Steps
            </p>
            <ol
              className="mt-3 list-decimal space-y-3 pl-5 text-base leading-relaxed"
              style={{ color: 'var(--text-primary)' }}
            >
              {recommendation.recommended_steps.map((step, idx) => (
                <li key={`${recommendation.id}-${idx}`}>{step}</li>
              ))}
            </ol>
          </div>

          <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>
            <span className="font-medium" style={{ color: 'var(--text-muted)' }}>
              Estimated impact:
            </span>{' '}
            {recommendation.estimated_impact}
          </p>
        </div>
      ) : selectedAssetId ? (
        <p className="mt-4 text-sm" style={{ color: 'var(--text-muted)' }}>
          No recommendation available yet.
        </p>
      ) : (
        <p className="mt-4 text-sm" style={{ color: 'var(--text-muted)' }}>
          Select an asset to view the operator playbook.
        </p>
      )}
    </section>
  )
}
