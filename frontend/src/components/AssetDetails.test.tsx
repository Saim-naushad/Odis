import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { AssetDetails } from './AssetDetails'
import type { MonitoringAssetLatestResponse, MonitoringRunDetailsResponse } from '../types/monitoring'

const latest: MonitoringAssetLatestResponse = {
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
  decision_plan: { id: 'plan-1', priority: 'low', recommendation: 'Monitor' },
}

const runDetails: MonitoringRunDetailsResponse = {
  run_id: 'run-1',
  started_at: '2026-01-01T10:00:00Z',
  observations: [],
  reasoning_trace: null,
  structured_assessment: null,
  operational_situation: latest.operational_situation,
  decision_context: {
    id: 'ctx-1',
    goal_id: 'goal-1',
    situation_id: 'sit-1',
    assessment: 'ok',
    created_at: '2026-01-01T10:00:00Z',
  },
  decision_plan: {
    ...latest.decision_plan,
    context_id: 'ctx-1',
    created_at: '2026-01-01T10:00:00Z',
    justification: 'because',
  },
  trend_analysis: {
    direction: 'rising',
    rate_of_change: 1.25,
    stability_score: 82,
    volatility_score: 15,
    summary: 'Temperature increased steadily across the last 5 observations.',
  },
}

describe('AssetDetails', () => {
  it('renders Trend analysis section when present', () => {
    render(<AssetDetails latest={latest} runDetails={runDetails} loading={false} />)

    expect(screen.getByText('Trend analysis')).toBeInTheDocument()
    expect(screen.getByText('rising')).toBeInTheDocument()
    expect(screen.getByText('82/100')).toBeInTheDocument()
    expect(screen.getByText('15/100')).toBeInTheDocument()
    expect(
      screen.getByText('Temperature increased steadily across the last 5 observations.'),
    ).toBeInTheDocument()
  })
})

