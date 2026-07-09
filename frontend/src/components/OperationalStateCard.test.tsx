import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { OperationalStateCard } from './OperationalStateCard'
import type { OperationalStateResponse } from '../types/monitoring'

describe('OperationalStateCard', () => {
  it('renders empty state when no asset is selected', () => {
    render(
      <OperationalStateCard
        selectedAssetId={undefined}
        operationalState={undefined}
        loading={false}
      />,
    )

    expect(screen.getByText('Operational state')).toBeInTheDocument()
    expect(
      screen.getByText('Select an asset to view its operational state.'),
    ).toBeInTheDocument()
  })

  it('renders operational state fields', () => {
    const state: OperationalStateResponse = {
      asset_id: 'asset-1',
      health_score: 82,
      health_status: 'NORMAL',
      risk_level: 'LOW',
      confidence: 77,
      primary_driver: 'Trend: Temperature remained stable across the last 5 observations.',
      recommended_action: 'Continue routine monitoring.',
      last_updated: '2026-01-01T10:00:00Z',
    }

    render(
      <OperationalStateCard
        selectedAssetId="asset-1"
        operationalState={state}
        loading={false}
      />,
    )

    expect(screen.getByText('82/100')).toBeInTheDocument()
    expect(screen.getByText(/Status: NORMAL/)).toBeInTheDocument()
    expect(screen.getByText(/Risk: LOW/)).toBeInTheDocument()
    expect(screen.getByText(/Confidence: 77\/100/)).toBeInTheDocument()
    expect(screen.getByText(/Primary driver:/)).toBeInTheDocument()
    expect(screen.getByText(/Recommended action:/)).toBeInTheDocument()
    expect(screen.getByText(/Continue routine monitoring\./)).toBeInTheDocument()
  })
})

