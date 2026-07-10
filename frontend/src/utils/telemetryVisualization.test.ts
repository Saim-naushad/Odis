import { describe, expect, it } from 'vitest'
import {
  defaultResolutionForRange,
  extractMeasurementTypes,
  getTimeWindow,
  prepareAggregateChartData,
  prepareRawChartData,
  sortSamplesChronologically,
} from './telemetryVisualization'
import type {
  TelemetryAggregateSeriesResponse,
  TelemetrySeriesResponse,
} from '../types/monitoring'

describe('telemetryVisualization utilities', () => {
  it('maps time ranges to sensible default resolutions', () => {
    expect(defaultResolutionForRange('1h')).toBe('raw')
    expect(defaultResolutionForRange('24h')).toBe('hourly')
    expect(defaultResolutionForRange('7d')).toBe('hourly')
    expect(defaultResolutionForRange('30d')).toBe('daily')
  })

  it('builds inclusive ISO time windows', () => {
    const now = new Date('2026-07-10T12:00:00.000Z')
    const window = getTimeWindow('24h', now)

    expect(window.end).toBe('2026-07-10T12:00:00.000Z')
    expect(window.start).toBe('2026-07-09T12:00:00.000Z')
  })

  it('sorts samples chronologically', () => {
    const sorted = sortSamplesChronologically([
      { timestamp: '2026-01-03T00:00:00Z', value: 3 },
      { timestamp: '2026-01-01T00:00:00Z', value: 1 },
      { timestamp: '2026-01-02T00:00:00Z', value: 2 },
    ])

    expect(sorted.map((sample) => sample.value)).toEqual([1, 2, 3])
  })

  it('prepares raw chart data in chronological order', () => {
    const series: TelemetrySeriesResponse = {
      asset_id: 'asset-1',
      measurement_type: 'stack_temperature',
      unit: 'C',
      samples: [
        { timestamp: '2026-01-02T00:00:00Z', value: 70 },
        { timestamp: '2026-01-01T00:00:00Z', value: 65 },
      ],
    }

    const chartData = prepareRawChartData(series)

    expect(chartData).toHaveLength(2)
    expect(chartData[0].value).toBe(65)
    expect(chartData[1].value).toBe(70)
    expect(chartData[0].label).toBeTruthy()
  })

  it('prepares aggregate chart data with min/max metadata', () => {
    const series: TelemetryAggregateSeriesResponse = {
      asset_id: 'asset-1',
      measurement_type: 'stack_temperature',
      unit: 'C',
      bucket: '1h',
      samples: [
        {
          timestamp: '2026-01-01T01:00:00Z',
          avg_value: 68,
          min_value: 60,
          max_value: 72,
          sample_count: 12,
        },
      ],
    }

    const chartData = prepareAggregateChartData(series, 'hourly')

    expect(chartData[0]).toMatchObject({
      avg_value: 68,
      min_value: 60,
      max_value: 72,
      sample_count: 12,
    })
  })

  it('extracts unique measurement types', () => {
    const types = extractMeasurementTypes([
      { measurement_type: 'humidity' },
      { measurement_type: 'stack_temperature' },
      { measurement_type: 'humidity' },
    ])

    expect(types).toEqual(['humidity', 'stack_temperature'])
  })
})
