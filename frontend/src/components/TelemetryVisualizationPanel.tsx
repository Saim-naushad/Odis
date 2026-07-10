import type { CSSProperties } from 'react'
import { TelemetryChart } from './TelemetryChart'
import { TelemetryEmptyState } from './monitoring/TelemetryEmptyState'
import { useTelemetryVisualization } from '../hooks/useTelemetryVisualization'
import type { MonitoringSseConnectionState } from '../monitoring/useMonitoringSse'
import {
  prepareAggregateChartData,
  prepareRawChartData,
  type TelemetryResolution,
  type TelemetryTimeRange,
} from '../utils/telemetryVisualization'

interface TelemetryVisualizationPanelProps {
  assetId?: string
  sseConnectionState?: MonitoringSseConnectionState
}

const TIME_RANGE_OPTIONS: Array<{
  value: TelemetryTimeRange
  label: string
}> = [
  { value: '1h', label: 'Last hour' },
  { value: '24h', label: 'Last 24 hours' },
  { value: '7d', label: 'Last 7 days' },
  { value: '30d', label: 'Last 30 days' },
]

const RESOLUTION_OPTIONS: Array<{
  value: TelemetryResolution
  label: string
}> = [
  { value: 'raw', label: 'Raw' },
  { value: 'hourly', label: 'Hourly' },
  { value: 'daily', label: 'Daily' },
]

function controlButtonClass(isActive: boolean): string {
  return `rounded border px-2 py-0.5 text-[10px] uppercase tracking-wide transition-colors ${
    isActive ? 'focus-ring-active' : 'hover:opacity-80'
  }`
}

function controlButtonStyle(isActive: boolean): CSSProperties {
  return {
    borderColor: isActive ? 'var(--focus-ring)' : 'var(--surface-border)',
    color: isActive ? 'var(--text-primary)' : 'var(--text-muted)',
    background: isActive ? 'var(--surface-raised)' : 'transparent',
  }
}

export function TelemetryVisualizationPanel({
  assetId,
  sseConnectionState,
}: TelemetryVisualizationPanelProps) {
  const viz = useTelemetryVisualization({ assetId, sseConnectionState })

  const rawChartData = prepareRawChartData(
    viz.selectedRawSeries,
    viz.resolution,
  )
  const aggregateChartData = prepareAggregateChartData(
    viz.selectedAggregateSeries,
    viz.resolution,
  )
  const unit =
    viz.resolution === 'raw'
      ? viz.selectedRawSeries?.unit
      : viz.selectedAggregateSeries?.unit

  return (
    <section
      className="flex h-full min-h-[360px] flex-col rounded border p-4"
      style={{
        borderColor: 'var(--surface-border)',
        background: 'var(--surface-raised)',
      }}
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2
            className="text-xs font-semibold uppercase tracking-wide"
            style={{ color: 'var(--text-secondary)' }}
          >
            Telemetry
          </h2>
          <p className="mt-1 text-[10px]" style={{ color: 'var(--text-muted)' }}>
            Measurement history and trend investigation
          </p>
        </div>
      </div>

      {!assetId ? (
        <div className="mt-4 flex flex-1 flex-col">
          <TelemetryEmptyState variant="no-asset" />
        </div>
      ) : (
        <div className="mt-4 flex flex-1 flex-col gap-3">
          <div className="flex flex-wrap items-end gap-3">
            <fieldset className="min-w-0">
              <legend
                className="mb-1 text-[10px] uppercase tracking-wide"
                style={{ color: 'var(--text-muted)' }}
              >
                Measurement
              </legend>
              {viz.availableMeasurements.length > 1 ? (
                <label className="sr-only" htmlFor="telemetry-measurement">
                  Measurement type
                </label>
              ) : null}
              {viz.availableMeasurements.length > 1 ? (
                <select
                  id="telemetry-measurement"
                  className="rounded border px-2 py-1 text-[11px]"
                  style={{
                    borderColor: 'var(--surface-border)',
                    background: 'var(--surface-base)',
                    color: 'var(--text-primary)',
                  }}
                  value={viz.selectedMeasurement ?? ''}
                  onChange={(event) =>
                    viz.setSelectedMeasurement(event.target.value)
                  }
                >
                  {viz.availableMeasurements.map((measurement) => (
                    <option key={measurement} value={measurement}>
                      {measurement}
                    </option>
                  ))}
                </select>
              ) : (
                <p className="text-[11px]" style={{ color: 'var(--text-secondary)' }}>
                  {viz.selectedMeasurement ?? 'No measurements available'}
                </p>
              )}
            </fieldset>

            <fieldset>
              <legend
                className="mb-1 text-[10px] uppercase tracking-wide"
                style={{ color: 'var(--text-muted)' }}
              >
                Time range
              </legend>
              <div className="flex flex-wrap gap-1" role="group" aria-label="Time range">
                {TIME_RANGE_OPTIONS.map((option) => (
                  <button
                    key={option.value}
                    type="button"
                    className={controlButtonClass(viz.timeRange === option.value)}
                    style={controlButtonStyle(viz.timeRange === option.value)}
                    aria-pressed={viz.timeRange === option.value}
                    onClick={() => viz.setTimeRange(option.value)}
                  >
                    {option.label}
                  </button>
                ))}
              </div>
            </fieldset>

            <fieldset>
              <legend
                className="mb-1 text-[10px] uppercase tracking-wide"
                style={{ color: 'var(--text-muted)' }}
              >
                Resolution
              </legend>
              <div
                className="flex flex-wrap gap-1"
                role="group"
                aria-label="Telemetry resolution"
              >
                {RESOLUTION_OPTIONS.map((option) => (
                  <button
                    key={option.value}
                    type="button"
                    className={controlButtonClass(
                      viz.resolution === option.value,
                    )}
                    style={controlButtonStyle(viz.resolution === option.value)}
                    aria-pressed={viz.resolution === option.value}
                    onClick={() => viz.setResolution(option.value)}
                  >
                    {option.label}
                  </button>
                ))}
              </div>
            </fieldset>
          </div>

          {viz.availableMeasurements.length > 1 && unit && (
            <p className="text-[10px]" style={{ color: 'var(--text-muted)' }}>
              Metrics with different units are shown one at a time so values stay
              comparable on a single axis.
            </p>
          )}

          <TelemetryChart
            mode={viz.resolution === 'raw' ? 'raw' : 'aggregate'}
            measurementType={viz.selectedMeasurement}
            unit={unit}
            resolution={viz.resolution}
            rawData={rawChartData}
            aggregateData={aggregateChartData}
            loading={viz.loading}
            error={viz.error}
            onRetry={viz.retry}
          />
        </div>
      )}
    </section>
  )
}
