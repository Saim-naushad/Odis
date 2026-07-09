import { useEffect, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { createSseClient } from '../api/sseClient'
import { createMonitoringEventDispatcher } from './monitoringEventDispatcher'
import type { MonitoringSsePayload } from './monitoringEventTypes'

const MONITORING_EVENTS_URL = '/api/monitoring/events'

export type MonitoringSseConnectionState =
  | 'connecting'
  | 'connected'
  | 'disconnected'

export interface UseMonitoringSseResult {
  connectionState: MonitoringSseConnectionState
}

export function useMonitoringSse(): UseMonitoringSseResult {
  const queryClient = useQueryClient()
  const [connectionState, setConnectionState] =
    useState<MonitoringSseConnectionState>('connecting')
  const hasConnectedRef = useRef(false)

  useEffect(() => {
    const dispatcher = createMonitoringEventDispatcher(queryClient)
    const client = createSseClient<MonitoringSsePayload>({
      url: MONITORING_EVENTS_URL,
      onOpen: () => {
        if (hasConnectedRef.current) {
          dispatcher.invalidateAll()
        } else {
          hasConnectedRef.current = true
        }
        setConnectionState('connected')
        console.info('[monitoring:sse] connected')
      },
      onError: (error) => {
        const source = error.target
        if (source instanceof EventSource) {
          setConnectionState(
            source.readyState === EventSource.CONNECTING
              ? 'connecting'
              : 'disconnected',
          )
        } else {
          setConnectionState('disconnected')
        }
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
      setConnectionState('disconnected')
      console.info('[monitoring:sse] disconnected')
    }
  }, [queryClient])

  return { connectionState }
}
