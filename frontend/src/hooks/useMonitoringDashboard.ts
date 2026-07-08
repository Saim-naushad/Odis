import { useEffect, useMemo, useState } from 'react'
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

  const pollIntervalMs = useMemo(
    () => options?.pollIntervalMs ?? DEFAULT_POLL_INTERVAL_MS,
    [options?.pollIntervalMs],
  )

  // Platform health + metadata
  useEffect(() => {
    let cancelled = false

    async function fetchPlatform() {
      try {
        const [health, meta] = await Promise.all([
          monitoringClient.getHealth(),
          monitoringClient.getPlatformMetadata(),
        ])
        if (cancelled) return
        setPlatformStatus(health.status === 'ok' ? 'ok' : 'error')
        setPlatformName(meta.platform_name)
        setReasoningEngineVersion(meta.reasoning_engine_version)
        setPlatformPhase(meta.platform_phase)
        setPlatformErrorMessage(undefined)
      } catch (error) {
        if (cancelled) return
        setPlatformStatus('error')
        setPlatformErrorMessage(
          error instanceof Error ? error.message : 'Failed to reach platform',
        )
      }
    }

    fetchPlatform()
    const timer = setInterval(fetchPlatform, pollIntervalMs)

    return () => {
      cancelled = true
      clearInterval(timer)
    }
  }, [pollIntervalMs])

  // Assets list
  useEffect(() => {
    let cancelled = false

    async function fetchAssets() {
      setAssetsLoading(true)
      setAssetsError(undefined)
      try {
        const data = await monitoringClient.listAssets()
        if (cancelled) return
        setAssets(data)
        if (!selectedAssetId && data.length > 0) {
          setSelectedAssetId(data[0].id)
        }
      } catch (error) {
        if (cancelled) return
        setAssetsError(
          error instanceof Error ? error.message : 'Failed to load assets',
        )
      } finally {
        if (!cancelled) {
          setAssetsLoading(false)
        }
      }
    }

    fetchAssets()
    const timer = setInterval(fetchAssets, pollIntervalMs)

    return () => {
      cancelled = true
      clearInterval(timer)
    }
  }, [pollIntervalMs, selectedAssetId])

  // Latest + history for selected asset
  useEffect(() => {
    if (!selectedAssetId) {
      setLatestForAsset(undefined)
      setHistory([])
      setSelectedRunId(undefined)
      return
    }

    let cancelled = false

    async function fetchLatestAndHistory() {
      setLatestLoading(true)
      setHistoryLoading(true)
      setLatestError(undefined)
      setHistoryError(undefined)

      try {
        const [latest, historyItems] = await Promise.all([
          monitoringClient.getLatestForAsset(selectedAssetId),
          monitoringClient.getHistoryForAsset(selectedAssetId),
        ])
        if (cancelled) return

        setLatestForAsset(latest)
        setHistory(historyItems)
        setLastUpdatedAt(new Date())

        if (!selectedRunId) {
          setSelectedRunId(latest.run_id)
        }
      } catch (error) {
        if (cancelled) return
        const message =
          error instanceof Error ? error.message : 'Failed to load asset data'
        setLatestError(message)
        setHistoryError(message)
      } finally {
        if (!cancelled) {
          setLatestLoading(false)
          setHistoryLoading(false)
        }
      }
    }

    fetchLatestAndHistory()
    const timer = setInterval(fetchLatestAndHistory, pollIntervalMs)

    return () => {
      cancelled = true
      clearInterval(timer)
    }
  }, [pollIntervalMs, selectedAssetId, selectedRunId])

  // Run details for selected run
  useEffect(() => {
    if (!selectedRunId) {
      setRunDetails(undefined)
      return
    }

    let cancelled = false

    async function fetchRunDetails() {
      setRunDetailsLoading(true)
      setRunDetailsError(undefined)
      try {
        const details = await monitoringClient.getRunDetails(selectedRunId)
        if (cancelled) return
        setRunDetails(details)
      } catch (error) {
        if (cancelled) return
        setRunDetailsError(
          error instanceof Error
            ? error.message
            : 'Failed to load run details',
        )
      } finally {
        if (!cancelled) {
          setRunDetailsLoading(false)
        }
      }
    }

    fetchRunDetails()
    const timer = setInterval(fetchRunDetails, pollIntervalMs)

    return () => {
      cancelled = true
      clearInterval(timer)
    }
  }, [pollIntervalMs, selectedRunId])

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
  }
}

