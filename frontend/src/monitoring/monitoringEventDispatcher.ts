import type { QueryClient } from '@tanstack/react-query'
import type { MonitoringSsePayload } from './monitoringEventTypes'

// Every SSE message still invalidates immediately (no batching/debouncing —
// updates stay real-time), but cancelRefetch: false leaves an already
// in-flight fetch for that query alone instead of aborting and restarting it.
// The query is still marked invalidated, so the next SSE message after the
// in-flight fetch resolves triggers a fresh fetch as usual; staleness is
// bounded to at most one in-flight round-trip and self-heals continuously
// under the sustained SSE traffic this dashboard sees.
const NO_RESTART_IN_FLIGHT = { cancelRefetch: false }

export function createMonitoringEventDispatcher(queryClient: QueryClient) {
  return {
    invalidateAll(): void {
      void queryClient.invalidateQueries(
        { queryKey: ['monitoring'] },
        NO_RESTART_IN_FLIGHT,
      )
    },

    dispatch(payload: MonitoringSsePayload): void {
      switch (payload.type) {
        case 'asset_updated':
          if (payload.asset_id) {
            void queryClient.invalidateQueries(
              { queryKey: ['monitoring', 'assets'] },
              NO_RESTART_IN_FLIGHT,
            )
            void queryClient.invalidateQueries(
              {
                queryKey: [
                  'monitoring',
                  'asset',
                  payload.asset_id,
                  'latest+history',
                ],
                exact: true,
              },
              NO_RESTART_IN_FLIGHT,
            )
            void queryClient.invalidateQueries(
              {
                queryKey: ['monitoring', 'asset', payload.asset_id, 'digital-twin'],
                exact: true,
              },
              NO_RESTART_IN_FLIGHT,
            )
          }
          break
        case 'run_updated':
          if (payload.run_id) {
            void queryClient.invalidateQueries(
              {
                queryKey: ['monitoring', 'run', payload.run_id],
                exact: true,
              },
              NO_RESTART_IN_FLIGHT,
            )
          }
          break
        case 'platform_updated':
          void queryClient.invalidateQueries(
            { queryKey: ['monitoring', 'platform'] },
            NO_RESTART_IN_FLIGHT,
          )
          break
        case 'fault_investigation_updated':
          if (payload.asset_id) {
            void queryClient.invalidateQueries(
              {
                queryKey: [
                  'monitoring',
                  'asset',
                  payload.asset_id,
                  'fault-investigation',
                ],
                exact: true,
              },
              NO_RESTART_IN_FLIGHT,
            )
            void queryClient.invalidateQueries(
              {
                queryKey: [
                  'monitoring',
                  'asset',
                  payload.asset_id,
                  'fault-investigation-history',
                ],
                exact: true,
              },
              NO_RESTART_IN_FLIGHT,
            )
            // New ai_fault_* timeline entries surface through the
            // digital-twin's timeline_preview, not a separate query.
            void queryClient.invalidateQueries(
              {
                queryKey: ['monitoring', 'asset', payload.asset_id, 'digital-twin'],
                exact: true,
              },
              NO_RESTART_IN_FLIGHT,
            )
          }
          break
        default:
          break
      }
    },
  }
}

export type MonitoringEventDispatcher = ReturnType<
  typeof createMonitoringEventDispatcher
>
