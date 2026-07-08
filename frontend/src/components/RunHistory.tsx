import type { MonitoringAssetHistoryItemResponse } from '../types/monitoring'

interface RunHistoryProps {
  history: MonitoringAssetHistoryItemResponse[]
  selectedRunId?: string
  onSelectRun: (runId: string) => void
  loading: boolean
  error?: string
  onRetry?: () => void | Promise<void>
}

export function RunHistory({
  history,
  selectedRunId,
  onSelectRun,
  loading,
  error,
  onRetry,
}: RunHistoryProps) {
  const sorted = [...history].sort(
    (a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime(),
  )

  return (
    <section className="flex h-full flex-col rounded border border-slate-800 bg-slate-900/40 p-4">
      <div className="flex items-center justify-between gap-2">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-300">
          History
        </h2>
        {loading && !error && (
          <span className="text-[10px] uppercase tracking-wide text-slate-500">
            Refreshing…
          </span>
        )}
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
      <div className="mt-3 flex-1 overflow-y-auto rounded border border-slate-800 bg-slate-950/60">
        {sorted.length > 0 ? (
          <ul className="divide-y divide-slate-800 text-xs">
            {sorted.map((item) => {
              const isSelected = item.run_id === selectedRunId
              return (
                <li key={item.run_id}>
                  <button
                    type="button"
                    onClick={() => onSelectRun(item.run_id)}
                    className={`flex w-full items-start justify-between gap-3 px-3 py-2 text-left ${
                      isSelected
                        ? 'bg-slate-900/90'
                        : 'hover:bg-slate-900/60'
                    }`}
                  >
                    <div className="space-y-1">
                      <div className="flex items-center gap-2">
                        <span className="font-mono text-[10px] text-slate-300">
                          {item.run_id}
                        </span>
                        <span className="rounded bg-slate-800 px-2 py-0.5 text-[10px] text-slate-200">
                          {item.decision_plan.priority.toUpperCase()}
                        </span>
                      </div>
                      <p className="line-clamp-2 text-[11px] text-slate-200">
                        {item.decision_plan.recommendation}
                      </p>
                    </div>
                    <div className="flex flex-col items-end text-[10px] text-slate-500">
                      <span>
                        {new Date(item.timestamp).toLocaleTimeString()}
                      </span>
                      <span>
                        {new Date(item.timestamp).toLocaleDateString()}
                      </span>
                    </div>
                  </button>
                </li>
              )
            })}
          </ul>
        ) : !error && loading ? (
          <div className="flex h-full items-center justify-center px-3 py-6">
            <p className="text-xs text-slate-500">Loading history…</p>
          </div>
        ) : (
          !error && (
            <p className="px-3 py-2 text-xs text-slate-500">
              No reasoning runs recorded for this asset yet.
            </p>
          )
        )}
      </div>
    </section>
  )
}

