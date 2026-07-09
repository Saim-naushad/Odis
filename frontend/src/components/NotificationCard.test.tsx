import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { NotificationCard } from './NotificationCard'
import type { NotificationResponse, RecommendationResponse } from '../types/monitoring'

describe('NotificationCard', () => {
  it('renders empty state when no asset is selected', () => {
    render(
      <NotificationCard
        selectedAssetId={undefined}
        notification={undefined}
        recommendation={undefined}
        loading={false}
      />,
    )

    expect(screen.getByText('Notification')).toBeInTheDocument()
    expect(
      screen.getByText('Select an asset to view its latest notification.'),
    ).toBeInTheDocument()
  })

  it('renders notification fields and linked recommendation title', () => {
    const notification: NotificationResponse = {
      id: 'notif-rec-1',
      asset_id: 'asset-1',
      recommendation_id: 'rec-1',
      severity: 'CRITICAL',
      status: 'OPEN',
      title: 'Immediate mitigation required',
      message: 'Operational state indicates elevated risk requiring immediate action.',
      created_at: '2026-01-01T10:00:00Z',
    }

    const recommendation: RecommendationResponse = {
      id: 'rec-1',
      asset_id: 'asset-1',
      category: 'mitigate',
      priority: 'P1',
      urgency: 'IMMEDIATE',
      title: 'Immediate mitigation required',
      description: 'Take action now.',
      recommended_steps: ['Step 1'],
      estimated_impact: 'Reduce outage likelihood.',
      created_at: '2026-01-01T10:00:00Z',
    }

    render(
      <NotificationCard
        selectedAssetId="asset-1"
        notification={notification}
        recommendation={recommendation}
        loading={false}
      />,
    )

    expect(screen.getByText('CRITICAL')).toBeInTheDocument()
    expect(screen.getByText('OPEN')).toBeInTheDocument()
    expect(screen.getAllByText('Immediate mitigation required').length).toBeGreaterThan(0)
    expect(screen.getByText(/Operational state indicates elevated risk/)).toBeInTheDocument()
  })
})

