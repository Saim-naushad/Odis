import { QueryClient } from '@tanstack/react-query'
import { describe, expect, it, vi } from 'vitest'
import { createMonitoringEventDispatcher } from './monitoringEventDispatcher'

describe('createMonitoringEventDispatcher', () => {
  it('invalidates the active investigation, history, and digital-twin queries on fault_investigation_updated', () => {
    const queryClient = new QueryClient()
    const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries')
    const dispatcher = createMonitoringEventDispatcher(queryClient)

    dispatcher.dispatch({
      type: 'fault_investigation_updated',
      asset_id: 'asset-1',
      timestamp: '2026-01-01T10:00:00Z',
    })

    expect(invalidateSpy).toHaveBeenCalledWith(
      {
        queryKey: ['monitoring', 'asset', 'asset-1', 'fault-investigation'],
        exact: true,
      },
      { cancelRefetch: false },
    )
    expect(invalidateSpy).toHaveBeenCalledWith(
      {
        queryKey: ['monitoring', 'asset', 'asset-1', 'fault-investigation-history'],
        exact: true,
      },
      { cancelRefetch: false },
    )
    expect(invalidateSpy).toHaveBeenCalledWith(
      {
        queryKey: ['monitoring', 'asset', 'asset-1', 'digital-twin'],
        exact: true,
      },
      { cancelRefetch: false },
    )
  })

  it('does nothing for fault_investigation_updated without an asset_id', () => {
    const queryClient = new QueryClient()
    const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries')
    const dispatcher = createMonitoringEventDispatcher(queryClient)

    dispatcher.dispatch({ type: 'fault_investigation_updated' })

    expect(invalidateSpy).not.toHaveBeenCalled()
  })

  it('ignores unknown event types', () => {
    const queryClient = new QueryClient()
    const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries')
    const dispatcher = createMonitoringEventDispatcher(queryClient)

    dispatcher.dispatch({ type: 'some_future_event', asset_id: 'asset-1' })

    expect(invalidateSpy).not.toHaveBeenCalled()
  })
})
