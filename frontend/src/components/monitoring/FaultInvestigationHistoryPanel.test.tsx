import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { FaultInvestigationHistoryPanel } from './FaultInvestigationHistoryPanel'
import type { FaultInvestigationSummaryResponse } from '../../types/monitoring'

afterEach(cleanup)

const historyItem: FaultInvestigationSummaryResponse = {
  investigation_id: 'inv-1',
  asset_id: 'asset-1',
  investigation_status: 'RESOLVED',
  diagnosed_fault_class: 'cooling_degradation',
  previous_diagnosed_fault_class: null,
  alert_transition_type: 'cleared',
  observed_at: '2026-01-01T10:00:00Z',
  corroboration_result: 'corroborated',
  corroboration_notes: 'stack_temperature is increasing.',
  corroboration_rule_ids: [],
  urgency: null,
  recommendation_status: null,
  recommendation: null,
  authority_boundary_note: 'This fault was detected by a diagnostic model.',
  supporting_evidence: [],
  provenance: null,
}

const defaultProps = {
  onRetry: () => {},
}

describe('FaultInvestigationHistoryPanel', () => {
  it('shows a loading message while fetching', () => {
    render(
      <FaultInvestigationHistoryPanel {...defaultProps} history={[]} loading error={undefined} />,
    )

    expect(screen.getByText('Loading investigation history…')).toBeInTheDocument()
  })

  it('shows a normal empty state when there is no history', () => {
    render(<FaultInvestigationHistoryPanel {...defaultProps} history={[]} loading={false} />)

    expect(
      screen.getByText('No prior AI-detected fault investigations for this asset.'),
    ).toBeInTheDocument()
  })

  it('shows an error and a retry action when the fetch fails with no cached history', () => {
    const onRetry = vi.fn()
    render(
      <FaultInvestigationHistoryPanel
        history={[]}
        loading={false}
        error="Failed to load fault investigation history"
        onRetry={onRetry}
      />,
    )

    expect(
      screen.getByText('Failed to load fault investigation history'),
    ).toBeInTheDocument()
    expect(
      screen.queryByText('No prior AI-detected fault investigations for this asset.'),
    ).not.toBeInTheDocument()
  })

  it('renders history items', () => {
    render(
      <FaultInvestigationHistoryPanel {...defaultProps} history={[historyItem]} loading={false} />,
    )

    expect(screen.getByText('cooling degradation')).toBeInTheDocument()
    expect(screen.getByText('RESOLVED')).toBeInTheDocument()
    expect(screen.getByText('corroborated')).toBeInTheDocument()
  })

  it('keeps a previously-loaded history list visible when a background refresh fails', () => {
    // Regression: React Query keeps `data` populated across a failed
    // background refetch, so `history` (non-empty) and `error` can both be
    // truthy at once — the last-good list must stay on screen.
    render(
      <FaultInvestigationHistoryPanel
        {...defaultProps}
        history={[historyItem]}
        loading={false}
        error="Refresh failed: network error"
      />,
    )

    expect(screen.getByText('Refresh failed: network error')).toBeInTheDocument()
    expect(screen.getByText('cooling degradation')).toBeInTheDocument()
  })
})
