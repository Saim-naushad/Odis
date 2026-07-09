import type { QueryClient } from '@tanstack/react-query'
import type { MonitoringSsePayload } from './monitoringEventTypes'

export function createMonitoringEventDispatcher(queryClient: QueryClient) {
  return {
    dispatch(payload: MonitoringSsePayload): void {
      switch (payload.type) {
        case 'asset_updated':
          if (payload.asset_id) {
            void queryClient.invalidateQueries({
              queryKey: ['monitoring', 'assets'],
            })
            void queryClient.invalidateQueries({
              queryKey: [
                'monitoring',
                'asset',
                payload.asset_id,
                'latest+history',
              ],
              exact: true,
            })
          }
          break
        case 'run_updated':
          if (payload.run_id) {
            void queryClient.invalidateQueries({
              queryKey: ['monitoring', 'run', payload.run_id],
              exact: true,
            })
          }
          break
        case 'platform_updated':
          void queryClient.invalidateQueries({
            queryKey: ['monitoring', 'platform'],
          })
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
