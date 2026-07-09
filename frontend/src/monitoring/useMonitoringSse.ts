import { useEffect } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { createSseClient } from '../api/sseClient'
import { createMonitoringEventDispatcher } from './monitoringEventDispatcher'
import type { MonitoringSsePayload } from './monitoringEventTypes'

const MONITORING_EVENTS_URL = '/api/monitoring/events'

export function useMonitoringSse(): void {
  const queryClient = useQueryClient()

  useEffect(() => {
    const dispatcher = createMonitoringEventDispatcher(queryClient)
    const client = createSseClient<MonitoringSsePayload>({
      url: MONITORING_EVENTS_URL,
      onOpen: () => {
        console.info('[monitoring:sse] connected')
      },
      onError: (error) => {
        console.warn('[monitoring:sse] error', error)
      },
    })

    client.addEventListener('heartbeat', (event) => {
      const data = client.parse(event.data)
      console.debug('[monitoring:sse] heartbeat', data)
    })

    client.addEventListener('monitoring', (event) => {
      const payload = client.parse(event.data)
      console.debug('[monitoring:sse] monitoring event', payload)
      dispatcher.dispatch(payload)
    })

    return () => {
      client.close()
      console.info('[monitoring:sse] disconnected')
    }
  }, [queryClient])
}
