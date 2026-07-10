import type { TelemetryAggregateSeriesResponse } from '../types/monitoring'

export type TelemetryAggregateBucket = '1h' | '1d'

interface AggregateSummaryPanelProps {
  hourlySeries: TelemetryAggregateSeriesResponse[]
  dailySeries: TelemetryAggregateSeriesResponse[]
  selectedBucket: TelemetryAggregateBucket
  onBucketChange: (bucket: TelemetryAggregateBucket) => void
  loading: boolean
  error?: string
  onRetry?: () => void | Promise<void>
}

function formatBucketTime(timestamp: string, bucket: TelemetryAggregateBucket): string {
  const date = new Date(timestamp)
  if (bucket === '1d') {
    return date.toLocaleDateString()
  }
  return `${date.toLocaleDateString()} ${date.toLocaleTimeString([], {
    hour: '2-digit',
    minute: '2-digit',
  })}`
}

export function AggregateSummaryPanel({
  hourlySeries,
  dailySeries,
  selectedBucket,
  onBucketChange,
  loading,
  error,
  onRetry,
}: AggregateSummaryPanelProps) {
  const activeSeries =
    selectedBucket === '1h' ? hourlySeries : dailySeries
  const sortedSeries = [...activeSeries].sort((left, right) =>
    left.measurement_type.localeCompare(right.measurement_type),
  )

  return (
    <section className="flex h-full flex-col rounded border border-slate-800 bg-slate-900/40 p-4">
      <div className="flex items-center justify-between gap-2">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-300">
          Aggregate Summary
        </h2>
        <div className="flex items-center gap-1">
          <button
            type="button"
            className={`rounded border px-2 py-0.5 text-[10px] uppercase tracking-wide transition-colors ${
              selectedBucket === '1h'
                ? 'border-sky-500 text-sky-300'
                : 'border-slate-700 text-slate-400 hover:border-slate-500'
            }`}
            onClick={() => onBucketChange('1h')}
          >
            Hourly
          </button>
          <button
            type="button"
            className={`rounded border px-2 py-0.5 text-[10px] uppercase tracking-wide transition-colors ${
              selectedBucket === '1d'
                ? 'border-sky-500 text-sky-300'
                : 'border-slate-700 text-slate-400 hover:border-slate-500'
            }`}
            onClick={() => onBucketChange('1d')}
          >
            Daily
          </button>
        </div>
      </div>
      {loading && !error && (
        <p className="mt-2 text-[10px] uppercase tracking-wide text-slate-500">
          Refreshing…
        </p>
      )}
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
                        className="rounded border border-slate-800/80 px-2 py-1.5"
                      >
                        <div className="flex items-center justify-between gap-3 text-[11px]">
                          <span className="font-mono text-slate-200">
                            avg {sample.avg_value}
                          </span>
                          <span className="text-[10px] text-slate-500">
                            {formatBucketTime(sample.timestamp, selectedBucket)}
                          </span>
                        </div>
                        <div className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5 text-[10px] text-slate-500">
                          <span>min {sample.min_value}</span>
                          <span>max {sample.max_value}</span>
                          <span>{sample.sample_count} samples</span>
                        </div>
                      </li>
                    ))}
                </ul>
              </div>
            ))}
          </div>
        ) : !error && loading ? (
          <div className="flex h-full items-center justify-center px-3 py-6">
            <p className="text-xs text-slate-500">Loading aggregates…</p>
          </div>
        ) : (
          !error && (
            <p className="px-3 py-2 text-xs text-slate-500">
              No aggregate data available for this asset yet.
            </p>
          )
        )}
      </div>
    </section>
  )
}
