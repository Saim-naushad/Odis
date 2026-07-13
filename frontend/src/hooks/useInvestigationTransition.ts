import { useMutation, useQueryClient } from '@tanstack/react-query'
import { monitoringClient } from '../api/monitoringClient'
import type {
  DigitalTwinResponse,
  InvestigationTransitionRequest,
  InvestigationTransitionResponse,
} from '../types/monitoring'

/**
 * Records any operator investigation transition (acknowledge, start
 * investigating, resolve). Intentionally not named after a single status —
 * it accepts whichever status the caller requests so future transitions
 * don't need a new hook.
 */
export function useInvestigationTransition(assetId: string | undefined) {
  const queryClient = useQueryClient()

  return useMutation<InvestigationTransitionResponse, Error, InvestigationTransitionRequest>({
    mutationFn: (payload) => {
      if (!assetId) {
        return Promise.reject(new Error('No asset selected'))
      }
      return monitoringClient.recordInvestigationTransition(assetId, payload)
    },
    onSuccess: async (response) => {
      if (!assetId) return
      const queryKey = ['monitoring', 'asset', assetId, 'digital-twin']
      // The dashboard's SSE feed can be pushing frequent asset_updated events
      // (each reasoning cycle). Cancel any in-flight fetch for this query
      // before writing the operator's own confirmed result, otherwise a
      // fetch that started before this transition committed can resolve
      // afterwards and clobber it with stale data.
      await queryClient.cancelQueries({ queryKey, exact: true })
      queryClient.setQueryData<DigitalTwinResponse>(queryKey, (previous) =>
        previous ? { ...previous, investigation: response } : previous,
      )
      void queryClient.invalidateQueries({ queryKey, exact: true })
    },
  })
}
