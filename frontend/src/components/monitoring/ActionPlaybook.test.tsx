import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { ActionPlaybook } from './ActionPlaybook'
import type { RecommendationResponse } from '../../types/monitoring'

const recommendation: RecommendationResponse = {
  id: 'rec-1',
  asset_id: 'fc-stack-01',
  category: 'mitigate',
  priority: 'P1',
  urgency: 'IMMEDIATE',
  title: 'Reduce load and verify cooling',
  description: 'Take immediate steps to stabilize temperature.',
  recommended_steps: ['Check coolant pump', 'Inspect inlet valve'],
  estimated_impact: 'Prevent thermal runaway',
  created_at: '2026-01-01T10:00:00Z',
}

describe('ActionPlaybook', () => {
  it('renders recommendation steps once', () => {
    render(
      <ActionPlaybook
        selectedAssetId="fc-stack-01"
        recommendation={recommendation}
        loading={false}
      />,
    )

    expect(screen.getByText('Reduce load and verify cooling')).toBeInTheDocument()
    expect(screen.getByText('Check coolant pump')).toBeInTheDocument()
    expect(screen.getByText('Inspect inlet valve')).toBeInTheDocument()
    expect(screen.getByText(/Prevent thermal runaway/)).toBeInTheDocument()
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })
})
