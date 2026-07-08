import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { monitoringClient } from '../api/monitoringClient'
import type {
  MonitoringAssetHistoryItemResponse,
  MonitoringAssetLatestResponse,
  MonitoringAssetResponse,
  MonitoringRunDetailsResponse,
} from '../types/monitoring'

const DEFAULT_POLL_INTERVAL_MS = 5_000

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

  lastUpdatedAt?: Date
}

export interface UseMonitoringDashboardOptions {
  pollIntervalMs?: number
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
} {
  const [platformStatus, setPlatformStatus] =
    useState<MonitoringDashboardState['platformStatus']>('unknown')
  const [platformName, setPlatformName] = useState<string>()
  const [reasoningEngineVersion, setReasoningEngineVersion] = useState<string>()
  const [platformPhase, setPlatformPhase] = useState<string>()
  const [platformErrorMessage, setPlatformErrorMessage] = useState<string>()

  const [assets, setAssets] = useState<MonitoringAssetResponse[]>([])
  const [assetsLoading, setAssetsLoading] = useState(false)
  const [assetsError, setAssetsError] = useState<string>()

  const [selectedAssetId, setSelectedAssetId] = useState<string>()

  const [latestForAsset, setLatestForAsset] =
    useState<MonitoringAssetLatestResponse>()
  const [latestLoading, setLatestLoading] = useState(false)
  const [latestError, setLatestError] = useState<string>()

  const [history, setHistory] = useState<MonitoringAssetHistoryItemResponse[]>(
    [],
  )
  const [historyLoading, setHistoryLoading] = useState(false)
  const [historyError, setHistoryError] = useState<string>()

  const [selectedRunId, setSelectedRunId] = useState<string>()
  const [runDetails, setRunDetails] =
    useState<MonitoringRunDetailsResponse>()
  const [runDetailsLoading, setRunDetailsLoading] = useState(false)
  const [runDetailsError, setRunDetailsError] = useState<string>()

  const [lastUpdatedAt, setLastUpdatedAt] = useState<Date>()

  // Tracks whether we have ever successfully loaded data for the current panel.
  // Used only to differentiate initial load failures vs refresh failures in UX.
  const hasLoadedAssetsRef = useRef(false)
  const hasLoadedLatestHistoryRef = useRef(false)
  const hasLoadedHistoryRef = useRef(false)
  const hasLoadedRunDetailsRef = useRef(false)

  // Keep track of current selection without forcing effect restarts.
  const selectedAssetIdRef = useRef<string | undefined>(selectedAssetId)
  const selectedRunIdRef = useRef<string | undefined>(selectedRunId)
  selectedAssetIdRef.current = selectedAssetId
  selectedRunIdRef.current = selectedRunId

  // Prevent overlapping polling requests (single-flight per resource).
  const platformPollInFlightRef = useRef(false)
  const assetsPollInFlightRef = useRef(false)
  const latestHistoryPollInFlightRef = useRef(false)
  const runDetailsPollInFlightRef = useRef(false)

  // Prevent stale responses from older in-flight work overwriting newer state.
  const platformReqIdRef = useRef(0)
  const assetsReqIdRef = useRef(0)
  const latestHistoryReqIdRef = useRef(0)
  const runDetailsReqIdRef = useRef(0)

  const pollIntervalMs = useMemo(
    () => options?.pollIntervalMs ?? DEFAULT_POLL_INTERVAL_MS,
    [options?.pollIntervalMs],
  )

  // Reduce polling for resources that do not need frequent updates.
  const platformPollIntervalMs = Math.max(30_000, pollIntervalMs * 6)
  const assetsPollIntervalMs = Math.max(15_000, pollIntervalMs * 3)
  const runDetailsPollIntervalMs = Math.max(15_000, pollIntervalMs * 3)

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
      setLatestForAsset(undefined)
      setHistory([])
      setLatestLoading(false)
      setHistoryLoading(false)
      setLatestError(undefined)
      setHistoryError(undefined)

      setSelectedRunId(undefined)
      setRunDetails(undefined)
      setRunDetailsLoading(false)
      setRunDetailsError(undefined)

      setLastUpdatedAt(undefined)
      hasLoadedLatestHistoryRef.current = false
      hasLoadedHistoryRef.current = false
      hasLoadedRunDetailsRef.current = false
      return
    }

    setLatestForAsset(undefined)
    setHistory([])
    setLatestLoading(true)
    setHistoryLoading(true)
    setLatestError(undefined)
    setHistoryError(undefined)

    setSelectedRunId(undefined)
    setRunDetails(undefined)
    setRunDetailsLoading(false)
    setRunDetailsError(undefined)

    setLastUpdatedAt(undefined)

    hasLoadedLatestHistoryRef.current = false
    hasLoadedHistoryRef.current = false
    hasLoadedRunDetailsRef.current = false
  }, [selectedAssetId])

  // Platform health + metadata
  useEffect(() => {
    let cancelled = false

    async function fetchPlatform() {
      if (platformPollInFlightRef.current) return
      platformPollInFlightRef.current = true
      const requestId = ++platformReqIdRef.current

      try {
        const [health, meta] = await Promise.all([
          monitoringClient.getHealth(),
          monitoringClient.getPlatformMetadata(),
        ])
        if (cancelled || requestId !== platformReqIdRef.current) return
        setPlatformStatus(health.status === 'ok' ? 'ok' : 'error')
        setPlatformName(meta.platform_name)
        setReasoningEngineVersion(meta.reasoning_engine_version)
        setPlatformPhase(meta.platform_phase)
        setPlatformErrorMessage(undefined)
      } catch (error) {
        if (cancelled || requestId !== platformReqIdRef.current) return
        setPlatformStatus('error')
        setPlatformErrorMessage(
          error instanceof Error ? error.message : 'Failed to reach platform',
        )
      } finally {
        platformPollInFlightRef.current = false
      }
    }

    fetchPlatform()
    const timer = setInterval(fetchPlatform, platformPollIntervalMs)

    return () => {
      cancelled = true
      clearInterval(timer)
    }
  }, [platformPollIntervalMs])

  // Assets list
  useEffect(() => {
    let cancelled = false

    async function fetchAssets() {
      if (assetsPollInFlightRef.current) return
      assetsPollInFlightRef.current = true
      const requestId = ++assetsReqIdRef.current

      setAssetsLoading(true)
      setAssetsError(undefined)
      try {
        const data = await monitoringClient.listAssets()
        if (cancelled || requestId !== assetsReqIdRef.current) return
        setAssets(data)
        hasLoadedAssetsRef.current = true
        if (!selectedAssetIdRef.current && data.length > 0) {
          setSelectedAssetId(data[0].id)
        }
      } catch (error) {
        if (cancelled || requestId !== assetsReqIdRef.current) return
        setAssetsError(
          formatPhaseError(
            hasLoadedAssetsRef.current,
            error,
            'Failed to load assets',
            'Failed to refresh assets',
          ),
        )
      } finally {
        if (!cancelled) {
          setAssetsLoading(false)
        }
        assetsPollInFlightRef.current = false
      }
    }

    fetchAssets()
    const timer = setInterval(fetchAssets, assetsPollIntervalMs)

    return () => {
      cancelled = true
      clearInterval(timer)
    }
  }, [assetsPollIntervalMs])

  // Latest + history for selected asset
  useEffect(() => {
    if (!selectedAssetId) {
      setLatestForAsset(undefined)
      setHistory([])
      setSelectedRunId(undefined)
      return
    }

    const assetId: string = selectedAssetId
    let cancelled = false

    async function fetchLatestAndHistory() {
      if (latestHistoryPollInFlightRef.current) return
      latestHistoryPollInFlightRef.current = true
      const requestId = ++latestHistoryReqIdRef.current

      setLatestLoading(true)
      setHistoryLoading(true)
      setLatestError(undefined)
      setHistoryError(undefined)

      try {
        const [latest, historyItems] = await Promise.all([
          monitoringClient.getLatestForAsset(assetId),
          monitoringClient.getHistoryForAsset(assetId),
        ])
        if (
          cancelled ||
          requestId !== latestHistoryReqIdRef.current
        ) {
          return
        }

        setLatestForAsset(latest)
        setHistory(historyItems)
        setLastUpdatedAt(new Date())
        hasLoadedLatestHistoryRef.current = true
        hasLoadedHistoryRef.current = true

        if (!selectedRunIdRef.current) {
          setSelectedRunId(latest.run_id)
        }
      } catch (error) {
        if (
          cancelled ||
          requestId !== latestHistoryReqIdRef.current
        ) {
          return
        }
        setLatestError(
          formatPhaseError(
            hasLoadedLatestHistoryRef.current,
            error,
            'Failed to load asset data',
            'Failed to refresh asset data',
          ),
        )
        setHistoryError(
          formatPhaseError(
            hasLoadedHistoryRef.current,
            error,
            'Failed to load history',
            'Failed to refresh history',
          ),
        )
      } finally {
        if (!cancelled) {
          setLatestLoading(false)
          setHistoryLoading(false)
        }
        latestHistoryPollInFlightRef.current = false
      }
    }

    fetchLatestAndHistory()
    const timer = setInterval(fetchLatestAndHistory, pollIntervalMs)

    return () => {
      cancelled = true
      clearInterval(timer)
    }
  }, [pollIntervalMs, selectedAssetId])

  // Run details for selected run
  useEffect(() => {
    if (!selectedRunId) {
      setRunDetails(undefined)
      setRunDetailsLoading(false)
      setRunDetailsError(undefined)
      return
    }

    const runId: string = selectedRunId
    let cancelled = false

    // Prevent stale trace/details from a previous run from flashing while we load the new run.
    hasLoadedRunDetailsRef.current = false
    setRunDetails(undefined)
    setRunDetailsLoading(true)
    setRunDetailsError(undefined)

    async function fetchRunDetails() {
      if (runDetailsPollInFlightRef.current) return
      runDetailsPollInFlightRef.current = true
      const requestId = ++runDetailsReqIdRef.current

      try {
        const details = await monitoringClient.getRunDetails(runId)
        if (cancelled || requestId !== runDetailsReqIdRef.current) return
        setRunDetails(details)
        hasLoadedRunDetailsRef.current = true
      } catch (error) {
        if (cancelled || requestId !== runDetailsReqIdRef.current) return
        setRunDetailsError(
          formatPhaseError(
            hasLoadedRunDetailsRef.current,
            error,
            'Failed to load run details',
            'Failed to refresh run details',
          ),
        )
      } finally {
        if (!cancelled) {
          setRunDetailsLoading(false)
        }
        runDetailsPollInFlightRef.current = false
      }
    }

    fetchRunDetails()
    const timer = setInterval(fetchRunDetails, runDetailsPollIntervalMs)

    return () => {
      cancelled = true
      clearInterval(timer)
    }
  }, [runDetailsPollIntervalMs, selectedRunId])

  async function retryAssetList(): Promise<void> {
    setAssetsLoading(true)
    setAssetsError(undefined)
    let assetIdToLoad: string | undefined = selectedAssetId

    try {
      const data = await monitoringClient.listAssets()
      setAssets(data)
      hasLoadedAssetsRef.current = true

      if (!selectedAssetId && data.length > 0) {
        setSelectedAssetId(data[0].id)
        assetIdToLoad = data[0].id
      }
    } catch (error) {
      setAssetsError(
        formatPhaseError(
          hasLoadedAssetsRef.current,
          error,
          'Failed to load assets',
          'Failed to refresh assets',
        ),
      )
    } finally {
      setAssetsLoading(false)
    }

    // Asset list tiles also depend on selected-asset latest/history.
    if (assetIdToLoad) {
      await retryLatestAndHistory(assetIdToLoad)
    }
  }

  async function retryLatestAndHistory(assetIdOverride?: string): Promise<void> {
    const assetIdToLoad = assetIdOverride ?? selectedAssetId
    if (!assetIdToLoad) return

    setLatestLoading(true)
    setHistoryLoading(true)
    setLatestError(undefined)
    setHistoryError(undefined)

    try {
      const [latest, historyItems] = await Promise.all([
        monitoringClient.getLatestForAsset(assetIdToLoad),
        monitoringClient.getHistoryForAsset(assetIdToLoad),
      ])

      setLatestForAsset(latest)
      setHistory(historyItems)
      setLastUpdatedAt(new Date())
      hasLoadedLatestHistoryRef.current = true
      hasLoadedHistoryRef.current = true

      if (!selectedRunId) {
        setSelectedRunId(latest.run_id)
      }
    } catch (error) {
      setLatestError(
        formatPhaseError(
          hasLoadedLatestHistoryRef.current,
          error,
          'Failed to load asset data',
          'Failed to refresh asset data',
        ),
      )
      setHistoryError(
        formatPhaseError(
          hasLoadedHistoryRef.current,
          error,
          'Failed to load history',
          'Failed to refresh history',
        ),
      )
    } finally {
      setLatestLoading(false)
      setHistoryLoading(false)
    }
  }

  async function retryRunHistory(): Promise<void> {
    if (!selectedAssetId) return

    setHistoryLoading(true)
    setHistoryError(undefined)

    try {
      const historyItems = await monitoringClient.getHistoryForAsset(
        selectedAssetId,
      )
      setHistory(historyItems)
      hasLoadedHistoryRef.current = true
    } catch (error) {
      setHistoryError(
        formatPhaseError(
          hasLoadedHistoryRef.current,
          error,
          'Failed to load history',
          'Failed to refresh history',
        ),
      )
    } finally {
      setHistoryLoading(false)
    }
  }

  async function retryRunDetails(runIdOverride?: string): Promise<void> {
    const runId = runIdOverride ?? selectedRunId
    if (!runId) return

    setRunDetailsLoading(true)
    setRunDetailsError(undefined)

    try {
      const details = await monitoringClient.getRunDetails(runId)
      setRunDetails(details)
      hasLoadedRunDetailsRef.current = true
    } catch (error) {
      setRunDetailsError(
        formatPhaseError(
          hasLoadedRunDetailsRef.current,
          error,
          'Failed to load run details',
          'Failed to refresh run details',
        ),
      )
    } finally {
      setRunDetailsLoading(false)
    }
  }

  async function retryAssetDetails(): Promise<void> {
    if (!selectedAssetId) return

    // Retry latest + history for the selected asset.
    setLatestLoading(true)
    setHistoryLoading(true)
    setLatestError(undefined)
    setHistoryError(undefined)

    let latest: MonitoringAssetLatestResponse | undefined
    try {
      const [latestResult, historyItems] = await Promise.all([
        monitoringClient.getLatestForAsset(selectedAssetId),
        monitoringClient.getHistoryForAsset(selectedAssetId),
      ])
      latest = latestResult

      setLatestForAsset(latestResult)
      setHistory(historyItems)
      setLastUpdatedAt(new Date())
      hasLoadedLatestHistoryRef.current = true
      hasLoadedHistoryRef.current = true

      if (!selectedRunId) {
        setSelectedRunId(latestResult.run_id)
      }
    } catch (error) {
      setLatestError(
        formatPhaseError(
          hasLoadedLatestHistoryRef.current,
          error,
          'Failed to load asset data',
          'Failed to refresh asset data',
        ),
      )
      setHistoryError(
        formatPhaseError(
          hasLoadedHistoryRef.current,
          error,
          'Failed to load history',
          'Failed to refresh history',
        ),
      )
      return
    } finally {
      setLatestLoading(false)
      setHistoryLoading(false)
    }

    // Retry run details for the currently selected run (or the newest run if none yet).
    const runIdToFetch = selectedRunId ?? latest?.run_id
    if (runIdToFetch) {
      await retryRunDetails(runIdToFetch)
    }
  }

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
    lastUpdatedAt,
    setSelectedAssetId,
    setSelectedRunId,
    retryAssetList,
    retryAssetDetails,
    retryRunHistory,
    retryReasoningTrace: () => retryRunDetails(),
  }
}

