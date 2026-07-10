import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useMonitoringDashboard } from './useMonitoringDashboard'

vi.mock('../api/monitoringClient', () => {
  return {
    monitoringClient: {
      getHealth: vi.fn(async () => ({ status: 'ok' })),
      getPlatformMetadata: vi.fn(async () => ({
        platform_name: 'ODIS',
        reasoning_engine_version: 'test',
        platform_phase: 'dev',
      })),
      listAssets: vi.fn(async () => [{ id: 'asset-1' }]),
      getLatestForAsset: vi.fn(async () => ({
        asset_id: 'asset-1',
        run_id: 'run-1',
        timestamp: '2026-01-01T10:00:00Z',
        operational_situation: {
          id: 'sit-1',
          goal_id: 'goal-1',
          observation_ids: ['obs-1', 'obs-2'],
          assessment: 'ok',
        },
        structured_assessment: null,
        decision_plan: { id: 'plan-1', priority: 'P3', recommendation: 'monitor' },
      })),
      getHistoryForAsset: vi.fn(async () => [
        {
          asset_id: 'asset-1',
          run_id: 'run-1',
          timestamp: '2026-01-01T10:00:00Z',
          operational_situation: {
            id: 'sit-1',
            goal_id: 'goal-1',
            observation_ids: ['obs-1', 'obs-2'],
            assessment: 'ok',
          },
          structured_assessment: null,
          decision_plan: { id: 'plan-1', priority: 'P3', recommendation: 'monitor' },
        },
      ]),
      getRunDetails: vi.fn(async () => {
        throw new Error('not used')
      }),
      getDigitalTwinForAsset: vi.fn(async () => ({
        asset_id: 'asset-1',
        asset_name: 'Asset 1',
        asset_type: 'unknown',
        location: { identifier: 'unknown' },
        operational_state: {
          asset_id: 'asset-1',
          health_score: 90,
          health_status: 'NORMAL',
          risk_level: 'LOW',
          confidence: 80,
          primary_driver: 'ok',
          recommended_action: 'monitor',
          last_updated: '2026-01-01T10:00:00Z',
        },
        recommendation: {
          id: 'rec-1',
          asset_id: 'asset-1',
          category: 'monitor',
          priority: 'P3',
          urgency: 'SCHEDULED',
          title: 'Monitor',
          description: 'desc',
          recommended_steps: ['step'],
          estimated_impact: 'low',
          created_at: '2026-01-01T10:00:00Z',
        },
        notification: null,
        latest_reasoning_run_id: 'run-1',
        timeline_preview: [
          {
            id: 'evt-1',
            asset_id: 'asset-1',
            timestamp: '2026-01-01T10:00:00Z',
            event_type: 'reasoning_completed',
            title: 'Done',
            description: 'desc',
            metadata: {},
          },
        ],
        telemetry_forecasts: [],
        last_updated: '2026-01-01T10:00:00Z',
      })),
      // Legacy endpoints should not be called by the dashboard model.
      getTimelineForAsset: vi.fn(async () => {
        throw new Error('legacy endpoint should not be used')
      }),
      getOperationalStateForAsset: vi.fn(async () => {
        throw new Error('legacy endpoint should not be used')
      }),
      getRecommendationForAsset: vi.fn(async () => {
        throw new Error('legacy endpoint should not be used')
      }),
      getNotificationForAsset: vi.fn(async () => {
        throw new Error('legacy endpoint should not be used')
      }),
    },
  }
})

function Harness() {
  // Use connected to disable interval polling (timers) in tests.
  const state = useMonitoringDashboard({ sseConnectionState: 'connected' })
  return (
    <div>
      <div data-testid="asset">{state.selectedAssetId ?? ''}</div>
      <div data-testid="twin">{state.digitalTwin?.asset_id ?? ''}</div>
      <div data-testid="preview">
        {state.digitalTwin?.timeline_preview.length ?? 0}
      </div>
    </div>
  )
}

describe('useMonitoringDashboard (Digital Twin)', () => {
  afterEach(() => {
    cleanup()
  })

  it('uses Digital Twin as the page model', async () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false, staleTime: 0 } },
    })

    render(
      <QueryClientProvider client={queryClient}>
        <Harness />
      </QueryClientProvider>,
    )

    await waitFor(() => {
      expect(screen.getByTestId('asset')).toHaveTextContent('asset-1')
      expect(screen.getByTestId('twin')).toHaveTextContent('asset-1')
      expect(screen.getByTestId('preview')).toHaveTextContent('1')
    })

    await queryClient.cancelQueries()
    queryClient.clear()
  })
})

