import { useEffect, useRef } from 'react'
import { useQuery } from '@tanstack/react-query'
import { monitoringClient } from '../api/monitoringClient'
import type { MonitoringSseConnectionState } from '../monitoring/useMonitoringSse'
import type {
  FaultInvestigationDetailResponse,
  FaultInvestigationSummaryResponse,
} from '../types/monitoring'

/** Fallback poll interval when SSE is unavailable; SSE invalidation is primary. */
const DEFAULT_POLL_INTERVAL_MS = 60_000
const DEFAULT_HISTORY_LIMIT = 20

export interface UseFaultInvestigationOptions {
  pollIntervalMs?: number
  historyLimit?: number
  /**
   * SSE connection state from useMonitoringSse(). While 'connected', SSE
   * invalidation drives freshness and fallback polling is disabled entirely.
   */
  sseConnectionState?: MonitoringSseConnectionState
}

export interface FaultInvestigationState {
  activeInvestigation: FaultInvestigationSummaryResponse | null | undefined
  activeLoading: boolean
  activeError?: string

  history: FaultInvestigationSummaryResponse[]
  historyLoading: boolean
  historyError?: string

  retryActive: () => Promise<void>
  retryHistory: () => Promise<void>
}

/**
 * Reads the asset-scoped AI fault investigation read model (PR179).
 * Deliberately standalone, not folded into `useMonitoringDashboard`'s god
 * hook — mirrors `useInvestigationTransition`'s precedent of a focused hook
 * per concern. `activeInvestigation` is `undefined` while unloaded, `null`
 * when the asset genuinely has no active investigation (a normal state,
 * never an error), and populated when one exists.
 */
export function useFaultInvestigation(
  assetId: string | undefined,
  options?: UseFaultInvestigationOptions,
): FaultInvestigationState {
  const hasLoadedActiveRef = useRef(false)
  const hasLoadedHistoryRef = useRef(false)

  const pollIntervalMs = options?.pollIntervalMs ?? DEFAULT_POLL_INTERVAL_MS
  const historyLimit = options?.historyLimit ?? DEFAULT_HISTORY_LIMIT
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

    return hasLoadedBefore ? `Refresh failed: ${base}` : `Initial load failed: ${base}`
  }

  const activeQuery = useQuery({
    queryKey: ['monitoring', 'asset', assetId, 'fault-investigation'],
    enabled: Boolean(assetId),
    queryFn: ({ signal }) =>
      monitoringClient.getFaultInvestigationForAsset(assetId as string, signal),
    refetchInterval,
    refetchIntervalInBackground: true,
  })

  const historyQuery = useQuery({
    queryKey: ['monitoring', 'asset', assetId, 'fault-investigation-history'],
    enabled: Boolean(assetId),
    queryFn: ({ signal }) =>
      monitoringClient.getFaultInvestigationHistoryForAsset(assetId as string, signal, {
        limit: historyLimit,
      }),
    refetchInterval,
    refetchIntervalInBackground: true,
  })

  useEffect(() => {
    if (activeQuery.isSuccess) hasLoadedActiveRef.current = true
  }, [activeQuery.isSuccess])

  useEffect(() => {
    if (historyQuery.isSuccess) hasLoadedHistoryRef.current = true
  }, [historyQuery.isSuccess])

  const activeInvestigation = assetId
    ? activeQuery.data?.active_investigation
    : undefined
  // isLoading (not isFetching) so cached data stays visible without a flash
  // during SSE-triggered background refetches (matches useMonitoringDashboard).
  const activeLoading = Boolean(assetId) && activeQuery.isLoading
  const activeError =
    assetId && activeQuery.isError
      ? formatPhaseError(
          hasLoadedActiveRef.current,
          activeQuery.error,
          'Failed to load the active fault investigation',
          'Failed to refresh the active fault investigation',
        )
      : undefined

  const history = assetId ? historyQuery.data ?? [] : []
  const historyLoading = Boolean(assetId) && historyQuery.isLoading
  const historyError =
    assetId && historyQuery.isError
      ? formatPhaseError(
          hasLoadedHistoryRef.current,
          historyQuery.error,
          'Failed to load fault investigation history',
          'Failed to refresh fault investigation history',
        )
      : undefined

  return {
    activeInvestigation,
    activeLoading,
    activeError,
    history,
    historyLoading,
    historyError,
    retryActive: async () => {
      await activeQuery.refetch()
    },
    retryHistory: async () => {
      await historyQuery.refetch()
    },
  }
}

export interface FaultInvestigationDetailState {
  detail: FaultInvestigationDetailResponse | undefined
  loading: boolean
  error?: string
  retry: () => Promise<void>
}

/**
 * Resolves a single investigation_id (from an `ai_fault_*` timeline event's
 * metadata - see getTimelineEventInvestigationId) to its full detail record.
 * Standalone for the same reason useFaultInvestigation is: a focused hook
 * per concern, not folded into useMonitoringDashboard's god hook.
 */
export function useFaultInvestigationDetail(
  investigationId: string | undefined,
): FaultInvestigationDetailState {
  const hasLoadedRef = useRef(false)

  const query = useQuery({
    queryKey: ['monitoring', 'fault-investigation-detail', investigationId],
    enabled: Boolean(investigationId),
    queryFn: ({ signal }) =>
      monitoringClient.getFaultInvestigationDetail(investigationId as string, signal),
  })

  useEffect(() => {
    if (query.isSuccess) hasLoadedRef.current = true
  }, [query.isSuccess])

  const error =
    investigationId && query.isError
      ? query.error instanceof Error
        ? query.error.message
        : hasLoadedRef.current
          ? 'Failed to refresh the AI fault investigation detail'
          : 'Failed to load the AI fault investigation detail'
      : undefined

  return {
    detail: investigationId ? query.data : undefined,
    loading: Boolean(investigationId) && query.isLoading,
    error,
    retry: async () => {
      await query.refetch()
    },
  }
}
