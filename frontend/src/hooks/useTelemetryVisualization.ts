import { useEffect, useMemo, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { monitoringClient } from '../api/monitoringClient'
import type { MonitoringSseConnectionState } from '../monitoring/useMonitoringSse'
import type {
  TelemetryAggregateSeriesResponse,
  TelemetrySeriesResponse,
} from '../types/monitoring'
import {
  defaultResolutionForRange,
  extractMeasurementTypes,
  getTimeWindow,
  rawLimitForRange,
  resolutionToBucket,
  selectSeriesByMeasurement,
  type TelemetryResolution,
  type TelemetryTimeRange,
} from '../utils/telemetryVisualization'

const DEFAULT_POLL_INTERVAL_MS = 60_000

export interface UseTelemetryVisualizationOptions {
  assetId?: string
  pollIntervalMs?: number
  sseConnectionState?: MonitoringSseConnectionState
}

export function useTelemetryVisualization(
  options: UseTelemetryVisualizationOptions,
) {
  const { assetId, pollIntervalMs = DEFAULT_POLL_INTERVAL_MS, sseConnectionState } =
    options

  const [timeRange, setTimeRange] = useState<TelemetryTimeRange>('24h')
  const [resolution, setResolution] = useState<TelemetryResolution>(
    defaultResolutionForRange('24h'),
  )
  const [selectedMeasurement, setSelectedMeasurement] = useState<string>()

  const hasLoadedRef = useRef(false)

  const refetchInterval: number | false =
    sseConnectionState === 'connected' ? false : pollIntervalMs

  const timeWindow = getTimeWindow(timeRange)
  const bucket = resolutionToBucket(resolution)

  const telemetryQuery = useQuery({
    queryKey: [
      'monitoring',
      'asset',
      assetId,
      'telemetry-visualization',
      resolution,
      timeRange,
    ],
    enabled: Boolean(assetId),
    queryFn: async ({ signal }) => {
      const id = assetId as string
      if (resolution === 'raw') {
        return monitoringClient.getTelemetryHistoryForAsset(id, signal, {
          start: timeWindow.start,
          end: timeWindow.end,
          limit: rawLimitForRange(timeRange),
        })
      }

      const aggregates = await monitoringClient.getTelemetryAggregatesForAsset(
        id,
        signal,
        {
          bucket: bucket as '1h' | '1d',
          start: timeWindow.start,
          end: timeWindow.end,
        },
      )
      return aggregates
    },
    refetchInterval,
    refetchIntervalInBackground: true,
  })

  useEffect(() => {
    if (!assetId) {
      setSelectedMeasurement(undefined)
      hasLoadedRef.current = false
    }
  }, [assetId])

  useEffect(() => {
    if (telemetryQuery.isSuccess) {
      hasLoadedRef.current = true
    }
  }, [telemetryQuery.isSuccess])

  const availableMeasurements = useMemo(
    () =>
      extractMeasurementTypes(
        (telemetryQuery.data ?? []) as Array<{ measurement_type: string }>,
      ),
    [telemetryQuery.data],
  )

  useEffect(() => {
    if (availableMeasurements.length === 0) {
      setSelectedMeasurement(undefined)
      return
    }

    if (
      !selectedMeasurement ||
      !availableMeasurements.includes(selectedMeasurement)
    ) {
      setSelectedMeasurement(availableMeasurements[0])
    }
  }, [availableMeasurements, selectedMeasurement])

  function handleTimeRangeChange(nextRange: TelemetryTimeRange) {
    setTimeRange(nextRange)
    setResolution(defaultResolutionForRange(nextRange))
  }

  function handleResolutionChange(nextResolution: TelemetryResolution) {
    setResolution(nextResolution)
  }

  const selectedRawSeries = selectSeriesByMeasurement(
    resolution === 'raw'
      ? ((telemetryQuery.data ?? []) as TelemetrySeriesResponse[])
      : [],
    selectedMeasurement,
  )
  const selectedAggregateSeries = selectSeriesByMeasurement(
    resolution !== 'raw'
      ? ((telemetryQuery.data ?? []) as TelemetryAggregateSeriesResponse[])
      : [],
    selectedMeasurement,
  )

  // isLoading (not isFetching) so cached data stays visible without a
  // "Refreshing…" flash during SSE-triggered background refetches.
  const loading = Boolean(assetId) && telemetryQuery.isLoading
  const error =
    assetId && telemetryQuery.isError
      ? telemetryQuery.error instanceof Error
        ? hasLoadedRef.current
          ? `Refresh failed: ${telemetryQuery.error.message}`
          : `Initial load failed: ${telemetryQuery.error.message}`
        : hasLoadedRef.current
          ? 'Refresh failed: Failed to load telemetry'
          : 'Initial load failed: Failed to load telemetry'
      : undefined

  async function retry(): Promise<void> {
    if (!assetId) return
    await telemetryQuery.refetch()
  }

  return {
    timeRange,
    resolution,
    selectedMeasurement,
    availableMeasurements,
    selectedRawSeries,
    selectedAggregateSeries,
    loading,
    error,
    setTimeRange: handleTimeRangeChange,
    setResolution: handleResolutionChange,
    setSelectedMeasurement,
    retry,
  }
}
