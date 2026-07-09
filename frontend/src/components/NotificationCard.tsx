import type { NotificationResponse, RecommendationResponse } from '../types/monitoring'

interface NotificationCardProps {
  selectedAssetId?: string
  notification?: NotificationResponse
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

function severityVariant(severity: string): 'neutral' | 'info' | 'warn' | 'danger' {
  if (severity === 'CRITICAL') return 'danger'
  if (severity === 'WARNING') return 'warn'
  if (severity === 'INFO') return 'info'
  return 'neutral'
}

function statusVariant(status: string): 'neutral' | 'info' | 'warn' | 'danger' {
  if (status === 'OPEN') return 'warn'
  if (status === 'ACKNOWLEDGED') return 'info'
  if (status === 'RESOLVED') return 'neutral'
  return 'neutral'
}

export function NotificationCard({
  selectedAssetId,
  notification,
  recommendation,
  loading,
  error,
}: NotificationCardProps) {
  return (
    <section className="rounded border border-slate-800 bg-slate-900/40 p-4">
      <div className="flex items-center justify-between gap-2">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-300">
          Notification
        </h2>
        {loading && !error && (
          <span className="text-[10px] uppercase tracking-wide text-slate-500">
            Refreshing…
          </span>
        )}
      </div>

      {error ? (
        <p className="mt-2 text-xs text-amber-400">{error}</p>
      ) : notification ? (
        <div className="mt-3 grid gap-3 text-xs lg:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)]">
          <div className="rounded border border-slate-800 bg-slate-950/60 p-3">
            <div className="flex flex-wrap items-center gap-2">
              <span
                className={[
                  'inline-flex items-center rounded border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide',
                  badgeClasses(severityVariant(notification.severity)),
                ].join(' ')}
              >
                {notification.severity}
              </span>
              <span
                className={[
                  'inline-flex items-center rounded border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide',
                  badgeClasses(statusVariant(notification.status)),
                ].join(' ')}
              >
                {notification.status}
              </span>
              <span className="text-[10px] text-slate-500">
                Created: {new Date(notification.created_at).toLocaleString()}
              </span>
            </div>
            <p className="mt-2 text-sm font-semibold text-slate-50">
              {notification.title}
            </p>
            <p className="mt-2 text-[11px] leading-relaxed text-slate-200">
              {notification.message}
            </p>
          </div>

          <div className="rounded border border-slate-800 bg-slate-950/60 p-3">
            <p className="text-[10px] font-semibold uppercase tracking-wide text-slate-400">
              Linked recommendation
            </p>
            {recommendation ? (
              <>
                <p className="mt-2 text-[11px] font-semibold text-slate-50">
                  {recommendation.title}
                </p>
                <p className="mt-2 text-[11px] leading-relaxed text-slate-200">
                  {recommendation.description}
                </p>
              </>
            ) : (
              <p className="mt-2 text-[11px] text-slate-500">
                Recommendation details unavailable.
              </p>
            )}
          </div>
        </div>
      ) : selectedAssetId ? (
        <p className="mt-2 text-xs text-slate-500">No notification available.</p>
      ) : (
        <p className="mt-2 text-xs text-slate-500">
          Select an asset to view its latest notification.
        </p>
      )}
    </section>
  )
}

