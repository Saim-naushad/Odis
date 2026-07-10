import type { TelemetrySeriesResponse } from '../types/monitoring'

interface TelemetryHistoryPanelProps {
  series: TelemetrySeriesResponse[]
  loading: boolean
  error?: string
  onRetry?: () => void | Promise<void>
}

function formatSampleTime(timestamp: string): string {
  const date = new Date(timestamp)
  return `${date.toLocaleDateString()} ${date.toLocaleTimeString()}`
}

export function TelemetryHistoryPanel({
  series,
  loading,
  error,
  onRetry,
}: TelemetryHistoryPanelProps) {
  const sortedSeries = [...series].sort((left, right) =>
    left.measurement_type.localeCompare(right.measurement_type),
  )

  return (
    <section className="flex h-full flex-col rounded border border-slate-800 bg-slate-900/40 p-4">
      <div className="flex items-center justify-between gap-2">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-300">
          Telemetry History
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
        {sortedSeries.length > 0 ? (
          <div className="divide-y divide-slate-800">
            {sortedSeries.map((item) => (
              <div key={item.measurement_type} className="px-3 py-3">
                <div className="flex items-center justify-between gap-2">
                  <h3 className="text-[11px] font-semibold text-slate-200">
                    {item.measurement_type}
                  </h3>
                  <span className="text-[10px] text-slate-500">{item.unit}</span>
                </div>
                <ul className="mt-2 space-y-1">
                  {[...item.samples]
                    .sort(
                      (left, right) =>
                        new Date(right.timestamp).getTime() -
                        new Date(left.timestamp).getTime(),
                    )
                    .map((sample) => (
                      <li
                        key={`${item.measurement_type}-${sample.timestamp}`}
                        className="flex items-center justify-between gap-3 text-[11px]"
                      >
                        <span className="font-mono text-slate-300">
                          {sample.value}
                        </span>
                        <span className="text-[10px] text-slate-500">
                          {formatSampleTime(sample.timestamp)}
                        </span>
                      </li>
                    ))}
                </ul>
              </div>
            ))}
          </div>
        ) : !error && loading ? (
          <div className="flex h-full items-center justify-center px-3 py-6">
            <p className="text-xs text-slate-500">Loading telemetry…</p>
          </div>
        ) : (
          !error && (
            <p className="px-3 py-2 text-xs text-slate-500">
              No telemetry recorded for this asset yet.
            </p>
          )
        )}
      </div>
    </section>
  )
}
