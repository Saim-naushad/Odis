import type { RecommendationResponse } from '../types/monitoring'

interface RecommendationCardProps {
  selectedAssetId?: string
  recommendation?: RecommendationResponse
  loading: boolean
  error?: string
}

function badgeClasses(variant: 'neutral' | 'info' | 'warn' | 'danger') {
  switch (variant) {
    case 'danger':
      return 'border-rose-800/60 bg-rose-950/40 text-rose-200'
    case 'warn':
      return 'border-amber-800/60 bg-amber-950/40 text-amber-200'
    case 'info':
      return 'border-sky-800/60 bg-sky-950/40 text-sky-200'
    default:
      return 'border-slate-700 bg-slate-950/40 text-slate-200'
  }
}

function priorityVariant(priority: string): 'neutral' | 'info' | 'warn' | 'danger' {
  if (priority === 'P0') return 'danger'
  if (priority === 'P1') return 'warn'
  if (priority === 'P2') return 'info'
  return 'neutral'
}

export function RecommendationCard({
  selectedAssetId,
  recommendation,
  loading,
  error,
}: RecommendationCardProps) {
  return (
    <section className="rounded border border-slate-800 bg-slate-900/40 p-4">
      <div className="flex items-center justify-between gap-2">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-300">
          Recommendation
        </h2>
        {loading && !error && (
          <span className="text-[10px] uppercase tracking-wide text-slate-500">
            Refreshing…
          </span>
        )}
      </div>

      {error ? (
        <p className="mt-2 text-xs text-amber-400">{error}</p>
      ) : recommendation ? (
        <div className="mt-3 grid gap-4 text-xs lg:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)]">
          <div className="rounded border border-slate-800 bg-slate-950/60 p-3">
            <div className="flex flex-wrap items-center gap-2">
              <span
                className={[
                  'inline-flex items-center rounded border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide',
                  badgeClasses(priorityVariant(recommendation.priority)),
                ].join(' ')}
              >
                {recommendation.priority} · {recommendation.urgency}
              </span>
              <span className="inline-flex items-center rounded border border-slate-700 bg-slate-950/40 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-slate-200">
                {recommendation.category}
              </span>
              <span className="text-[10px] text-slate-500">
                Updated: {new Date(recommendation.created_at).toLocaleString()}
              </span>
            </div>
            <p className="mt-2 text-sm font-semibold text-slate-50">
              {recommendation.title}
            </p>
            <p className="mt-2 text-[11px] leading-relaxed text-slate-200">
              {recommendation.description}
            </p>
            <p className="mt-2 text-[11px] text-slate-300">
              <span className="text-slate-500">Estimated impact:</span>{' '}
              {recommendation.estimated_impact}
            </p>
          </div>

          <div className="rounded border border-slate-800 bg-slate-950/60 p-3">
            <p className="text-[10px] font-semibold uppercase tracking-wide text-slate-400">
              Recommended steps
            </p>
            <ol className="mt-2 list-decimal space-y-1 pl-4 text-[11px] text-slate-200">
              {recommendation.recommended_steps.map((step, idx) => (
                <li key={`${recommendation.id}-${idx}`}>{step}</li>
              ))}
            </ol>
          </div>
        </div>
      ) : selectedAssetId ? (
        <p className="mt-2 text-xs text-slate-500">
          No recommendation available yet.
        </p>
      ) : (
        <p className="mt-2 text-xs text-slate-500">
          Select an asset to view its recommendation.
        </p>
      )}
    </section>
  )
}

