import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, cleanup, renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useInvestigationTransition } from './useInvestigationTransition'
import type { InvestigationTransitionResponse } from '../types/monitoring'

const recordInvestigationTransition = vi.fn()

vi.mock('../api/monitoringClient', () => ({
  monitoringClient: {
    recordInvestigationTransition: (...args: unknown[]) =>
      recordInvestigationTransition(...args),
  },
}))

describe('useInvestigationTransition', () => {
  afterEach(() => {
    cleanup()
    recordInvestigationTransition.mockReset()
  })

  it('invalidates the digital twin query for the asset on success', async () => {
    const response: InvestigationTransitionResponse = {
      id: 'inv-1',
      asset_id: 'asset-1',
      recommendation_id: 'rec-1',
      status: 'ACKNOWLEDGED',
      actor_id: 'op-1',
      actor_display_name: 'op-1',
      occurred_at: '2026-01-01T10:00:00Z',
      notes: null,
    }
    recordInvestigationTransition.mockResolvedValue(response)

    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    })
    const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries')

    const wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    )

    const { result } = renderHook(() => useInvestigationTransition('asset-1'), {
      wrapper,
    })

    act(() => {
      result.current.mutate({
        recommendation_id: 'rec-1',
        status: 'ACKNOWLEDGED',
        actor_id: 'op-1',
        actor_display_name: 'op-1',
      })
    })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(recordInvestigationTransition).toHaveBeenCalledWith('asset-1', {
      recommendation_id: 'rec-1',
      status: 'ACKNOWLEDGED',
      actor_id: 'op-1',
      actor_display_name: 'op-1',
    })
    expect(invalidateSpy).toHaveBeenCalledWith({
      queryKey: ['monitoring', 'asset', 'asset-1', 'digital-twin'],
      exact: true,
    })
  })

  it('writes the confirmed transition into the digital twin cache immediately', async () => {
    const response: InvestigationTransitionResponse = {
      id: 'inv-2',
      asset_id: 'asset-1',
      recommendation_id: 'rec-1',
      status: 'INVESTIGATING',
      actor_id: 'op-1',
      actor_display_name: 'op-1',
      occurred_at: '2026-01-01T11:00:00Z',
      notes: null,
    }
    recordInvestigationTransition.mockResolvedValue(response)

    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    })
    const queryKey = ['monitoring', 'asset', 'asset-1', 'digital-twin']
    // Seed the cache as if a prior fetch (or a concurrent in-flight SSE
    // refetch) had returned the pre-transition state.
    queryClient.setQueryData(queryKey, {
      asset_id: 'asset-1',
      investigation: null,
    })

    const wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    )

    const { result } = renderHook(() => useInvestigationTransition('asset-1'), {
      wrapper,
    })

    act(() => {
      result.current.mutate({
        recommendation_id: 'rec-1',
        status: 'INVESTIGATING',
        actor_id: 'op-1',
        actor_display_name: 'op-1',
      })
    })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    // The operator's own confirmed result must be visible immediately,
    // regardless of whether a stale background refetch is still pending.
    expect(queryClient.getQueryData(queryKey)).toMatchObject({
      asset_id: 'asset-1',
      investigation: response,
    })
  })

  it('rejects without calling the API when no asset is selected', async () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    })
    const wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    )

    const { result } = renderHook(() => useInvestigationTransition(undefined), {
      wrapper,
    })

    act(() => {
      result.current.mutate({
        recommendation_id: 'rec-1',
        status: 'ACKNOWLEDGED',
        actor_id: 'op-1',
        actor_display_name: 'op-1',
      })
    })

    await waitFor(() => expect(result.current.isError).toBe(true))
    expect(recordInvestigationTransition).not.toHaveBeenCalled()
  })
})
