import type {
  TelemetryAggregateSampleResponse,
  TelemetryAggregateSeriesResponse,
  TelemetrySampleResponse,
  TelemetrySeriesResponse,
} from '../types/monitoring'

export type TelemetryTimeRange = '1h' | '24h' | '7d' | '30d'
export type TelemetryResolution = 'raw' | 'hourly' | 'daily'

export interface RawChartPoint {
  timestamp: string
  value: number
  label: string
}

export interface AggregateChartPoint {
  timestamp: string
  avg_value: number
  min_value: number
  max_value: number
  sample_count: number
  label: string
}

const HOUR_MS = 60 * 60 * 1000
const DAY_MS = 24 * HOUR_MS

export function defaultResolutionForRange(
  range: TelemetryTimeRange,
): TelemetryResolution {
  switch (range) {
    case '1h':
      return 'raw'
    case '24h':
    case '7d':
      return 'hourly'
    case '30d':
      return 'daily'
  }
}

export function getTimeWindow(
  range: TelemetryTimeRange,
  now: Date = new Date(),
): { start: string; end: string } {
  const end = now
  let start: Date

  switch (range) {
    case '1h':
      start = new Date(end.getTime() - HOUR_MS)
      break
    case '24h':
      start = new Date(end.getTime() - DAY_MS)
      break
    case '7d':
      start = new Date(end.getTime() - 7 * DAY_MS)
      break
    case '30d':
      start = new Date(end.getTime() - 30 * DAY_MS)
      break
  }

  return { start: start.toISOString(), end: end.toISOString() }
}

export function rawLimitForRange(range: TelemetryTimeRange): number {
  switch (range) {
    case '1h':
      return 500
    case '24h':
      return 2000
    case '7d':
      return 5000
    case '30d':
      return 10000
  }
}

export function resolutionToBucket(
  resolution: TelemetryResolution,
): '1h' | '1d' | null {
  switch (resolution) {
    case 'hourly':
      return '1h'
    case 'daily':
      return '1d'
    case 'raw':
      return null
  }
}

export function sortSamplesChronologically<T extends { timestamp: string }>(
  samples: T[],
): T[] {
  return [...samples].sort(
    (left, right) =>
      new Date(left.timestamp).getTime() - new Date(right.timestamp).getTime(),
  )
}

export function formatChartTimestamp(
  timestamp: string,
  resolution: TelemetryResolution,
): string {
  const date = new Date(timestamp)
  if (resolution === 'daily') {
    return date.toLocaleDateString()
  }
  if (resolution === 'hourly') {
    return date.toLocaleString(undefined, {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    })
  }
  return date.toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

export function extractMeasurementTypes(
  series: Array<{ measurement_type: string }>,
): string[] {
  return [...new Set(series.map((item) => item.measurement_type))].sort()
}

export function selectSeriesByMeasurement<T extends { measurement_type: string }>(
  series: T[],
  measurementType: string | undefined,
): T | undefined {
  if (!measurementType) return undefined
  return series.find((item) => item.measurement_type === measurementType)
}

export function prepareRawChartData(
  series: TelemetrySeriesResponse | undefined,
  resolution: TelemetryResolution = 'raw',
): RawChartPoint[] {
  if (!series) return []

  return sortSamplesChronologically(series.samples).map((sample) =>
    toRawChartPoint(sample, resolution),
  )
}

export function prepareAggregateChartData(
  series: TelemetryAggregateSeriesResponse | undefined,
  resolution: TelemetryResolution,
): AggregateChartPoint[] {
  if (!series) return []

  return sortSamplesChronologically(series.samples).map((sample) =>
    toAggregateChartPoint(sample, resolution),
  )
}

export function toRawChartPoint(
  sample: TelemetrySampleResponse,
  resolution: TelemetryResolution,
): RawChartPoint {
  return {
    timestamp: sample.timestamp,
    value: sample.value,
    label: formatChartTimestamp(sample.timestamp, resolution),
  }
}

export function toAggregateChartPoint(
  sample: TelemetryAggregateSampleResponse,
  resolution: TelemetryResolution,
): AggregateChartPoint {
  return {
    timestamp: sample.timestamp,
    avg_value: sample.avg_value,
    min_value: sample.min_value,
    max_value: sample.max_value,
    sample_count: sample.sample_count,
    label: formatChartTimestamp(sample.timestamp, resolution),
  }
}
