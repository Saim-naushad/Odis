import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { monitoringClient } from '../api/monitoringClient'
import type { MonitoringSseConnectionState } from '../monitoring/useMonitoringSse'
import type {
  DigitalTwinResponse,
  MonitoringAssetHistoryItemResponse,
  MonitoringAssetLatestResponse,
  MonitoringAssetResponse,
  MonitoringRunDetailsResponse,
  TelemetrySeriesResponse,
} from '../types/monitoring'

/** Fallback poll interval when SSE is unavailable; SSE invalidation is primary. */
const DEFAULT_POLL_INTERVAL_MS = 60_000

export interface MonitoringDashboardState {
  platformStatus: 'unknown' | 'ok' | 'error'
  platformName?: string
  reasoningEngineVersion?: string
  platformPhase?: string
  platformErrorMessage?: string

  assets: MonitoringAssetResponse[]
  assetsLoading: boolean
  assetsError?: string

  selectedAssetId?: string

  latestForAsset?: MonitoringAssetLatestResponse
  latestLoading: boolean
  latestError?: string

  history: MonitoringAssetHistoryItemResponse[]
  historyLoading: boolean
  historyError?: string

  selectedRunId?: string
  runDetails?: MonitoringRunDetailsResponse
  runDetailsLoading: boolean
  runDetailsError?: string

  digitalTwin?: DigitalTwinResponse
  digitalTwinLoading: boolean
  digitalTwinError?: string

  telemetryHistory: TelemetrySeriesResponse[]
  telemetryHistoryLoading: boolean
  telemetryHistoryError?: string

  lastUpdatedAt?: Date
}

export interface UseMonitoringDashboardOptions {
  pollIntervalMs?: number
  /**
   * SSE connection state from useMonitoringSse(). While 'connected', SSE
   * invalidation drives freshness and fallback polling is disabled entirely.
   */
  sseConnectionState?: MonitoringSseConnectionState
}

type LatestAndHistoryData = {
  latest: MonitoringAssetLatestResponse
  history: MonitoringAssetHistoryItemResponse[]
}

export function useMonitoringDashboard(
  options?: UseMonitoringDashboardOptions,
): MonitoringDashboardState & {
  setSelectedAssetId: (assetId: string | undefined) => void
  setSelectedRunId: (runId: string | undefined) => void
  retryAssetList: () => Promise<void>
  retryAssetDetails: () => Promise<void>
  retryRunHistory: () => Promise<void>
  retryReasoningTrace: () => Promise<void>
  retryTimeline: () => Promise<void>
  retryTelemetryHistory: () => Promise<void>
} {
  const queryClient = useQueryClient()
  const [selectedAssetId, setSelectedAssetId] = useState<string>()
  const [selectedRunId, setSelectedRunId] = useState<string>()

  // Tracks whether we have ever successfully loaded data for the current panel.
  // Used only to differentiate initial load failures vs refresh failures in UX.
  const hasLoadedAssetsRef = useRef(false)
  const hasLoadedLatestHistoryRef = useRef(false)
  const hasLoadedHistoryRef = useRef(false)
  const hasLoadedRunDetailsRef = useRef(false)
  const hasLoadedDigitalTwinRef = useRef(false)
  const hasLoadedTelemetryHistoryRef = useRef(false)

  // Keep track of current selection without forcing effect restarts.
  const selectedAssetIdRef = useRef<string | undefined>(selectedAssetId)
  const selectedRunIdRef = useRef<string | undefined>(selectedRunId)
  selectedAssetIdRef.current = selectedAssetId
  selectedRunIdRef.current = selectedRunId

  const pollIntervalMs = options?.pollIntervalMs ?? DEFAULT_POLL_INTERVAL_MS

  // Adaptive polling: while SSE is connected, event-driven invalidation keeps
  // queries fresh, so interval polling is disabled. When SSE is connecting or
  // disconnected, fall back to interval polling.
  const refetchInterval: number | false =
    options?.sseConnectionState === 'connected' ? false : pollIntervalMs

  function formatPhaseError(
    hasLoadedBefore: boolean,
    error: unknown,
    initialFallback: string,
    refreshFallback: string,
  ): string {
    const base =
      error instanceof Error
        ? error.message
        : hasLoadedBefore
          ? refreshFallback
          : initialFallback

    return hasLoadedBefore
      ? `Refresh failed: ${base}`
      : `Initial load failed: ${base}`
  }

  // Selection consistency: when the user switches assets, immediately clear run-scoped state
  // so panels can't briefly render stale data from the previously selected asset.
  useLayoutEffect(() => {
    if (!selectedAssetId) {
      setSelectedRunId(undefined)
      hasLoadedLatestHistoryRef.current = false
      hasLoadedHistoryRef.current = false
      hasLoadedRunDetailsRef.current = false
      hasLoadedDigitalTwinRef.current = false
      hasLoadedTelemetryHistoryRef.current = false
      return
    }

    setSelectedRunId(undefined)

    hasLoadedLatestHistoryRef.current = false
    hasLoadedHistoryRef.current = false
    hasLoadedRunDetailsRef.current = false
    hasLoadedDigitalTwinRef.current = false
    hasLoadedTelemetryHistoryRef.current = false
  }, [selectedAssetId])

  const platformQuery = useQuery({
    queryKey: ['monitoring', 'platform'],
    queryFn: async ({ signal }) => {
      const [health, meta] = await Promise.all([
        monitoringClient.getHealth(signal),
        monitoringClient.getPlatformMetadata(signal),
      ])
      return { health, meta }
    },
    refetchInterval,
    refetchIntervalInBackground: true,
  })

  const assetsQuery = useQuery({
    queryKey: ['monitoring', 'assets'],
    queryFn: ({ signal }) => monitoringClient.listAssets(signal),
    refetchInterval,
    refetchIntervalInBackground: true,
  })

  const latestAndHistoryQuery = useQuery<LatestAndHistoryData>({
    queryKey: ['monitoring', 'asset', selectedAssetId, 'latest+history'],
    enabled: Boolean(selectedAssetId),
    queryFn: async ({ signal }) => {
      const assetId = selectedAssetId as string
      const [latest, history] = await Promise.all([
        monitoringClient.getLatestForAsset(assetId, signal),
        monitoringClient.getHistoryForAsset(assetId, signal),
      ])
      return { latest, history }
    },
    refetchInterval,
    refetchIntervalInBackground: true,
  })

  const runDetailsQuery = useQuery({
    queryKey: ['monitoring', 'run', selectedRunId],
    enabled: Boolean(selectedRunId),
    queryFn: ({ signal }) => monitoringClient.getRunDetails(selectedRunId as string, signal),
    refetchInterval,
    refetchIntervalInBackground: true,
  })

  const digitalTwinQuery = useQuery({
    queryKey: ['monitoring', 'asset', selectedAssetId, 'digital-twin'],
    enabled: Boolean(selectedAssetId),
    queryFn: ({ signal }) =>
      monitoringClient.getDigitalTwinForAsset(selectedAssetId as string, signal),
    refetchInterval,
    refetchIntervalInBackground: true,
  })

  const telemetryHistoryQuery = useQuery({
    queryKey: ['monitoring', 'asset', selectedAssetId, 'telemetry-history'],
    enabled: Boolean(selectedAssetId),
    queryFn: ({ signal }) =>
      monitoringClient.getTelemetryHistoryForAsset(
        selectedAssetId as string,
        signal,
        { limit: 500 },
      ),
    refetchInterval,
    refetchIntervalInBackground: true,
  })

  // Preserve selection behavior: auto-select first asset when assets load.
  useEffect(() => {
    if (!assetsQuery.data || assetsQuery.data.length === 0) return
    if (!selectedAssetIdRef.current) {
      setSelectedAssetId(assetsQuery.data[0].id)
    }
  }, [assetsQuery.data])

  // Preserve selection behavior: auto-select newest run when asset latest loads.
  useEffect(() => {
    const latest = latestAndHistoryQuery.data?.latest
    if (!latest) return
    if (!selectedRunIdRef.current) {
      setSelectedRunId(latest.run_id)
    }
  }, [latestAndHistoryQuery.data])

  // Preserve initial-vs-refresh UX messaging.
  useEffect(() => {
    if (assetsQuery.isSuccess) hasLoadedAssetsRef.current = true
  }, [assetsQuery.isSuccess])

  useEffect(() => {
    if (latestAndHistoryQuery.isSuccess) {
      hasLoadedLatestHistoryRef.current = true
      hasLoadedHistoryRef.current = true
    }
  }, [latestAndHistoryQuery.isSuccess])

  useEffect(() => {
    if (runDetailsQuery.isSuccess) hasLoadedRunDetailsRef.current = true
  }, [runDetailsQuery.isSuccess])

  useEffect(() => {
    if (digitalTwinQuery.isSuccess) hasLoadedDigitalTwinRef.current = true
  }, [digitalTwinQuery.isSuccess])

  useEffect(() => {
    if (telemetryHistoryQuery.isSuccess) {
      hasLoadedTelemetryHistoryRef.current = true
    }
  }, [telemetryHistoryQuery.isSuccess])

  async function retryAssetList(): Promise<void> {
    const result = await assetsQuery.refetch()
    const assets = result.data
    const assetIdToLoad = selectedAssetIdRef.current ?? assets?.[0]?.id

    if (!selectedAssetIdRef.current && assets && assets.length > 0) {
      setSelectedAssetId(assets[0].id)
    }

    // Asset list tiles also depend on selected-asset latest/history.
    if (assetIdToLoad) {
      await retryLatestAndHistory(assetIdToLoad)
    }
  }

  async function retryLatestAndHistory(assetIdOverride?: string): Promise<void> {
    const assetIdToLoad = assetIdOverride ?? selectedAssetIdRef.current
    if (!assetIdToLoad) return

    // If we are retrying a non-selected asset, switch selection and refetch the
    // *target* query key (never the stale, previously-selected key).
    if (assetIdOverride && assetIdOverride !== selectedAssetIdRef.current) {
      setSelectedAssetId(assetIdOverride)
      await queryClient.refetchQueries({
        queryKey: ['monitoring', 'asset', assetIdOverride, 'latest+history'],
        exact: true,
      })
      return
    }

    await latestAndHistoryQuery.refetch()
  }

  async function retryRunHistory(): Promise<void> {
    if (!selectedAssetIdRef.current) return
    await latestAndHistoryQuery.refetch()
  }

  async function retryRunDetails(runIdOverride?: string): Promise<void> {
    const runId = runIdOverride ?? selectedRunIdRef.current
    if (!runId) return

    if (runIdOverride && runIdOverride !== selectedRunIdRef.current) {
      setSelectedRunId(runIdOverride)
      await queryClient.refetchQueries({
        queryKey: ['monitoring', 'run', runIdOverride],
        exact: true,
      })
      return
    }

    await runDetailsQuery.refetch()
  }

  async function retryAssetDetails(): Promise<void> {
    if (!selectedAssetIdRef.current) return

    const latestHistoryResult = await latestAndHistoryQuery.refetch()
    const runIdToFetch =
      selectedRunIdRef.current ?? latestHistoryResult.data?.latest.run_id

    // Retry run details for the currently selected run (or the newest run if none yet).
    if (runIdToFetch) {
      await retryRunDetails(runIdToFetch)
    }
  }

  async function retryDigitalTwin(): Promise<void> {
    if (!selectedAssetIdRef.current) return
    await digitalTwinQuery.refetch()
  }

  async function retryTelemetryHistory(): Promise<void> {
    if (!selectedAssetIdRef.current) return
    await telemetryHistoryQuery.refetch()
  }

  const platformStatus: MonitoringDashboardState['platformStatus'] =
    platformQuery.isLoading && !platformQuery.data
      ? 'unknown'
      : platformQuery.isError
        ? 'error'
        : platformQuery.data?.health.status === 'ok'
          ? 'ok'
          : 'error'

  const platformName = platformQuery.data?.meta.platform_name
  const reasoningEngineVersion =
    platformQuery.data?.meta.reasoning_engine_version
  const platformPhase = platformQuery.data?.meta.platform_phase
  const platformErrorMessage = platformQuery.isError
    ? platformQuery.error instanceof Error
      ? platformQuery.error.message
      : 'Failed to reach platform'
    : undefined

  const assets = assetsQuery.data ?? []
  const assetsLoading = assetsQuery.isFetching
  const assetsError = assetsQuery.isError
    ? formatPhaseError(
        hasLoadedAssetsRef.current,
        assetsQuery.error,
        'Failed to load assets',
        'Failed to refresh assets',
      )
    : undefined

  const latestForAsset = selectedAssetId
    ? latestAndHistoryQuery.data?.latest
    : undefined
  const history = selectedAssetId ? latestAndHistoryQuery.data?.history ?? [] : []
  const latestLoading = Boolean(selectedAssetId) && latestAndHistoryQuery.isFetching
  const historyLoading = Boolean(selectedAssetId) && latestAndHistoryQuery.isFetching
  const latestError =
    selectedAssetId && latestAndHistoryQuery.isError
      ? formatPhaseError(
          hasLoadedLatestHistoryRef.current,
          latestAndHistoryQuery.error,
          'Failed to load asset data',
          'Failed to refresh asset data',
        )
      : undefined
  const historyError =
    selectedAssetId && latestAndHistoryQuery.isError
      ? formatPhaseError(
          hasLoadedHistoryRef.current,
          latestAndHistoryQuery.error,
          'Failed to load history',
          'Failed to refresh history',
        )
      : undefined

  const runDetails =
    selectedRunId && selectedAssetId ? runDetailsQuery.data : undefined
  const runDetailsLoading =
    Boolean(selectedRunId) && Boolean(selectedAssetId) && runDetailsQuery.isFetching
  const runDetailsError =
    selectedRunId && runDetailsQuery.isError
      ? formatPhaseError(
          hasLoadedRunDetailsRef.current,
          runDetailsQuery.error,
          'Failed to load run details',
          'Failed to refresh run details',
        )
      : undefined

  const digitalTwin = selectedAssetId ? digitalTwinQuery.data : undefined
  const digitalTwinLoading = Boolean(selectedAssetId) && digitalTwinQuery.isFetching
  const digitalTwinError =
    selectedAssetId && digitalTwinQuery.isError
      ? formatPhaseError(
          hasLoadedDigitalTwinRef.current,
          digitalTwinQuery.error,
          'Failed to load digital twin',
          'Failed to refresh digital twin',
        )
      : undefined

  const telemetryHistory = selectedAssetId
    ? telemetryHistoryQuery.data ?? []
    : []
  const telemetryHistoryLoading =
    Boolean(selectedAssetId) && telemetryHistoryQuery.isFetching
  const telemetryHistoryError =
    selectedAssetId && telemetryHistoryQuery.isError
      ? formatPhaseError(
          hasLoadedTelemetryHistoryRef.current,
          telemetryHistoryQuery.error,
          'Failed to load telemetry history',
          'Failed to refresh telemetry history',
        )
      : undefined

  const lastUpdatedAt =
    selectedAssetId && latestAndHistoryQuery.data
      ? new Date(latestAndHistoryQuery.dataUpdatedAt)
      : undefined

  return {
    platformStatus,
    platformName,
    reasoningEngineVersion,
    platformPhase,
    platformErrorMessage,
    assets,
    assetsLoading,
    assetsError,
    selectedAssetId,
    latestForAsset,
    latestLoading,
    latestError,
    history,
    historyLoading,
    historyError,
    selectedRunId,
    runDetails,
    runDetailsLoading,
    runDetailsError,
    digitalTwin,
    digitalTwinLoading,
    digitalTwinError,
    telemetryHistory,
    telemetryHistoryLoading,
    telemetryHistoryError,
    lastUpdatedAt,
    setSelectedAssetId,
    setSelectedRunId,
    retryAssetList,
    retryAssetDetails,
    retryRunHistory,
    retryReasoningTrace: () => retryRunDetails(),
    retryTimeline: () => retryDigitalTwin(),
    retryTelemetryHistory,
  }
}

