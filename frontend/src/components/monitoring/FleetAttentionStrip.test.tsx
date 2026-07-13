import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { FleetAttentionStrip } from './FleetAttentionStrip'
import type { DigitalTwinResponse } from '../../types/monitoring'

const twin: DigitalTwinResponse = {
  asset_id: 'fc-stack-01',
  asset_name: 'FC Stack 01',
  asset_type: 'fuel_cell',
  location: { identifier: 'Bay 3' },
  operational_state: {
    asset_id: 'fc-stack-01',
    health_score: 62,
    health_status: 'WARNING',
    risk_level: 'MEDIUM',
    confidence: 74,
    primary_driver: 'Temperature rising',
    recommended_action: 'Investigate cooling',
    last_updated: '2026-01-01T10:00:00Z',
  },
  recommendation: {
    id: 'rec-1',
    asset_id: 'fc-stack-01',
    category: 'investigate',
    priority: 'P2',
    urgency: 'SOON',
    title: 'Investigate',
    description: 'Check cooling',
    recommended_steps: ['Step 1'],
    estimated_impact: 'medium',
    created_at: '2026-01-01T10:00:00Z',
  },
  notification: {
    id: 'notif-1',
    asset_id: 'fc-stack-01',
    recommendation_id: 'rec-1',
    severity: 'WARNING',
    status: 'OPEN',
    title: 'Warning',
    message: 'Temperature deviation',
    created_at: '2026-01-01T10:00:00Z',
  },
  investigation: null,
  latest_reasoning_run_id: 'run-1',
  timeline_preview: [],
  last_updated: '2026-01-01T10:00:00Z',
}

describe('FleetAttentionStrip', () => {
  afterEach(() => {
    cleanup()
  })

  it('shows rich status for selected asset only', () => {
    render(
      <FleetAttentionStrip
        assets={[{ id: 'fc-stack-01' }, { id: 'fc-stack-02' }]}
        selectedAssetId="fc-stack-01"
        selectedDigitalTwin={twin}
        loading={false}
        onSelectAsset={vi.fn()}
      />,
    )

    expect(screen.getByText('FC Stack 01')).toBeInTheDocument()
    expect(screen.getByText('WARNING')).toBeInTheDocument()
    expect(screen.getByText('62')).toBeInTheDocument()
    expect(screen.getByText('fc-stack-02')).toBeInTheDocument()
  })

  it('calls onSelectAsset when chip clicked', () => {
    const onSelectAsset = vi.fn()

    render(
      <FleetAttentionStrip
        assets={[{ id: 'fc-stack-01' }, { id: 'fc-stack-02' }]}
        selectedAssetId="fc-stack-01"
        selectedDigitalTwin={twin}
        loading={false}
        onSelectAsset={onSelectAsset}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: /fc-stack-02/i }))
    expect(onSelectAsset).toHaveBeenCalledWith('fc-stack-02')
  })
})
