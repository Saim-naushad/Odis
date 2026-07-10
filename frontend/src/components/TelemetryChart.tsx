import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import type {
  AggregateChartPoint,
  RawChartPoint,
  TelemetryResolution,
} from '../utils/telemetryVisualization'

type TelemetryChartMode = 'raw' | 'aggregate'

interface TelemetryChartProps {
  mode: TelemetryChartMode
  measurementType?: string
  unit?: string
  resolution: TelemetryResolution
  rawData?: RawChartPoint[]
  aggregateData?: AggregateChartPoint[]
  loading: boolean
  error?: string
  onRetry?: () => void | Promise<void>
}

function formatYAxisTick(value: number, unit?: string): string {
  const formatted = Number.isInteger(value) ? String(value) : value.toFixed(2)
  return unit ? `${formatted} ${unit}` : formatted
}

function RawTooltipContent({
  active,
  payload,
  unit,
}: {
  active?: boolean
  payload?: Array<{ payload: RawChartPoint }>
  unit?: string
}) {
  if (!active || !payload?.length) return null
  const point = payload[0].payload
  return (
    <div className="rounded border border-slate-700 bg-slate-900 px-3 py-2 text-xs shadow-lg">
      <p className="font-medium text-slate-100">{point.label}</p>
      <p className="mt-1 font-mono text-sky-300">
        {point.value}
        {unit ? ` ${unit}` : ''}
      </p>
    </div>
  )
}

function AggregateTooltipContent({
  active,
  payload,
  unit,
}: {
  active?: boolean
  payload?: Array<{ payload: AggregateChartPoint }>
  unit?: string
}) {
  if (!active || !payload?.length) return null
  const point = payload[0].payload
  return (
    <div className="rounded border border-slate-700 bg-slate-900 px-3 py-2 text-xs shadow-lg">
      <p className="font-medium text-slate-100">{point.label}</p>
      <dl className="mt-1 space-y-0.5 text-slate-300">
        <div className="flex justify-between gap-4">
          <dt>Avg</dt>
          <dd className="font-mono text-sky-300">
            {point.avg_value}
            {unit ? ` ${unit}` : ''}
          </dd>
        </div>
        <div className="flex justify-between gap-4">
          <dt>Min</dt>
          <dd className="font-mono">{point.min_value}</dd>
        </div>
        <div className="flex justify-between gap-4">
          <dt>Max</dt>
          <dd className="font-mono">{point.max_value}</dd>
        </div>
        <div className="flex justify-between gap-4">
          <dt>Samples</dt>
          <dd className="font-mono">{point.sample_count}</dd>
        </div>
      </dl>
    </div>
  )
}

export function TelemetryChart({
  mode,
  measurementType,
  unit,
  resolution,
  rawData = [],
  aggregateData = [],
  loading,
  error,
  onRetry,
}: TelemetryChartProps) {
  const hasData =
    mode === 'raw' ? rawData.length > 0 : aggregateData.length > 0
  const yAxisLabel = unit ? `Value (${unit})` : 'Value'
  const chartLabel = measurementType
    ? `${measurementType}${unit ? ` (${unit})` : ''}`
    : 'Telemetry'

  return (
    <div className="flex min-h-[220px] flex-1 flex-col">
      <div className="mb-2 flex items-center justify-between gap-2">
        <p className="text-[11px] font-medium text-slate-200" aria-live="polite">
          {chartLabel}
        </p>
        {loading && !error && (
          <span
            className="text-[10px] uppercase tracking-wide text-slate-500"
            role="status"
          >
            Refreshing…
          </span>
        )}
      </div>

      {error && (
        <div
          className="mb-2 flex items-start justify-between gap-2 rounded border border-amber-500/40 bg-amber-950/20 px-3 py-2"
          role="alert"
        >
          <p className="text-xs text-amber-300">{error}</p>
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

      <div
        className="flex flex-1 items-center justify-center rounded border border-slate-800 bg-slate-950/60 p-2"
        aria-label={chartLabel}
      >
        {!error && loading && !hasData ? (
          <p className="text-xs text-slate-500" role="status">
            Loading telemetry chart…
          </p>
        ) : !error && !hasData ? (
          <p className="text-xs text-slate-500">
            No telemetry data for the selected measurement and time range.
          </p>
        ) : !error && hasData ? (
          <ResponsiveContainer width="100%" height={220}>
            {mode === 'raw' ? (
              <LineChart
                data={rawData}
                margin={{ top: 8, right: 12, left: 4, bottom: 4 }}
              >
                <CartesianGrid stroke="#1e293b" strokeDasharray="3 3" />
                <XAxis
                  dataKey="label"
                  tick={{ fill: '#94a3b8', fontSize: 10 }}
                  interval="preserveStartEnd"
                  minTickGap={24}
                />
                <YAxis
                  tick={{ fill: '#94a3b8', fontSize: 10 }}
                  tickFormatter={(value: number) => formatYAxisTick(value, unit)}
                  label={{
                    value: yAxisLabel,
                    angle: -90,
                    position: 'insideLeft',
                    fill: '#94a3b8',
                    fontSize: 10,
                  }}
                />
                <Tooltip content={<RawTooltipContent unit={unit} />} />
                <Line
                  type="monotone"
                  dataKey="value"
                  stroke="#38bdf8"
                  strokeWidth={2}
                  dot={rawData.length <= 24}
                  activeDot={{ r: 4 }}
                  isAnimationActive={false}
                />
              </LineChart>
            ) : (
              <LineChart
                data={aggregateData}
                margin={{ top: 8, right: 12, left: 4, bottom: 4 }}
              >
                <CartesianGrid stroke="#1e293b" strokeDasharray="3 3" />
                <XAxis
                  dataKey="label"
                  tick={{ fill: '#94a3b8', fontSize: 10 }}
                  interval="preserveStartEnd"
                  minTickGap={24}
                />
                <YAxis
                  tick={{ fill: '#94a3b8', fontSize: 10 }}
                  tickFormatter={(value: number) => formatYAxisTick(value, unit)}
                  label={{
                    value: yAxisLabel,
                    angle: -90,
                    position: 'insideLeft',
                    fill: '#94a3b8',
                    fontSize: 10,
                  }}
                />
                <Tooltip content={<AggregateTooltipContent unit={unit} />} />
                <Line
                  type="monotone"
                  dataKey="avg_value"
                  stroke="#38bdf8"
                  strokeWidth={2}
                  dot={aggregateData.length <= 24}
                  activeDot={{ r: 4 }}
                  isAnimationActive={false}
                />
              </LineChart>
            )}
          </ResponsiveContainer>
        ) : null}
      </div>

      <p className="mt-2 text-[10px] text-slate-500">
        {resolution === 'raw'
          ? 'Showing raw samples from GET /monitoring/assets/{id}/telemetry.'
          : `Showing ${resolution} aggregates from GET /monitoring/assets/{id}/telemetry/aggregate.`}
      </p>
    </div>
  )
}
