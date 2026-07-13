import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { AssetStatusBar } from './AssetStatusBar'
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
    primary_driver: 'Stack temperature rising above expected band',
    recommended_action: 'Investigate cooling',
    last_updated: '2026-01-01T10:00:00Z',
  },
  recommendation: {
    id: 'rec-1',
    asset_id: 'fc-stack-01',
    category: 'investigate',
    priority: 'P2',
    urgency: 'SOON',
    title: 'Investigate cooling',
    description: 'Check cooling flow',
    recommended_steps: ['Step 1'],
    estimated_impact: 'medium',
    created_at: '2026-01-01T10:00:00Z',
  },
  notification: null,
  investigation: null,
  latest_reasoning_run_id: 'run-1',
  timeline_preview: [],
  last_updated: '2026-01-01T10:00:00Z',
}

describe('AssetStatusBar', () => {
  it('renders identity, health, risk, and primary driver', () => {
    render(
      <AssetStatusBar
        selectedAssetId="fc-stack-01"
        digitalTwin={twin}
        loading={false}
      />,
    )

    expect(screen.getByText('FC Stack 01')).toBeInTheDocument()
    expect(screen.getByText('62')).toBeInTheDocument()
    expect(screen.getByText('WARNING')).toBeInTheDocument()
    expect(screen.getByText('MEDIUM')).toBeInTheDocument()
    expect(screen.getByText('Risk')).toBeInTheDocument()
    expect(screen.getByText('74')).toBeInTheDocument()
    expect(screen.getByText(/Stack temperature rising/)).toBeInTheDocument()
    expect(screen.getByText(/Last assessed/)).toBeInTheDocument()
  })
})
