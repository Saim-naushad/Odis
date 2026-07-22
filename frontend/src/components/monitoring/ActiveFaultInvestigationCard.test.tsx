import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { ActiveFaultInvestigationCard } from './ActiveFaultInvestigationCard'
import type { FaultInvestigationSummaryResponse } from '../../types/monitoring'

afterEach(cleanup)

const baseInvestigation: FaultInvestigationSummaryResponse = {
  investigation_id: 'inv-1',
  asset_id: 'asset-1',
  investigation_status: 'OPEN',
  diagnosed_fault_class: 'cooling_degradation',
  previous_diagnosed_fault_class: null,
  alert_transition_type: 'confirmed',
  observed_at: '2026-01-01T10:00:00Z',
  corroboration_result: 'corroborated',
  corroboration_notes:
    'stack_temperature is increasing while coolant_flow is decreasing.',
  corroboration_rule_ids: ['cooling_degradation.stack_temperature_increasing'],
  urgency: 'ELEVATED',
  recommendation_status: 'produced',
  recommendation: {
    id: 'rec-1',
    status: 'produced',
    category: 'investigate',
    urgency: 'ELEVATED',
    action_summary: 'Inspect cooling subsystem',
    reason: 'Deterministic telemetry corroborated the alert.',
    recommended_steps: ['Check coolant pump', 'Verify flow sensor'],
    limitations: 'Automated inspection cannot substitute for a manual check.',
  },
  authority_boundary_note:
    'This fault was detected by a diagnostic model and is evidence, not a confirmed diagnosis.',
  supporting_evidence: [
    {
      observation_id: 'obs-1',
      measurement_type: 'stack_temperature',
      value: 70,
      unit: 'celsius',
      observed_at: '2026-01-01T09:58:00Z',
      role: 'supporting',
    },
  ],
  provenance: {
    model_system_version: 'plant_alpha_fault_v1',
    model_hash: 'hash-a',
    policy_hash: 'policy-a',
    feature_schema_version: '1.0',
    latest_model_score: 0.87,
    score_semantics:
      'This is an uncalibrated diagnostic ranking score, not a probability or confidence level.',
    source_event_id: 'evt-1',
    recorded_at: '2026-01-01T10:00:05Z',
  },
}

const defaultProps = {
  selectedAssetId: 'asset-1',
  onOpenHistory: () => {},
  historyDisabled: false,
}

describe('ActiveFaultInvestigationCard', () => {
  it('shows a prompt to select an asset when none is selected', () => {
    render(
      <ActiveFaultInvestigationCard
        {...defaultProps}
        selectedAssetId={undefined}
        investigation={undefined}
        loading={false}
      />,
    )

    expect(
      screen.getByText('Select an asset to view AI-assisted fault diagnosis.'),
    ).toBeInTheDocument()
  })

  it('shows a loading message while fetching', () => {
    render(
      <ActiveFaultInvestigationCard
        {...defaultProps}
        investigation={undefined}
        loading
      />,
    )

    expect(screen.getByText('Loading AI fault investigation…')).toBeInTheDocument()
  })

  it('shows an error message when the fetch fails', () => {
    render(
      <ActiveFaultInvestigationCard
        {...defaultProps}
        investigation={undefined}
        loading={false}
        error="Failed to load the active fault investigation"
      />,
    )

    expect(
      screen.getByText('Failed to load the active fault investigation'),
    ).toBeInTheDocument()
    // Must not claim "no active fault" — that would misreport an unknown
    // state (fetch failed) as a confirmed healthy one.
    expect(
      screen.queryByText('No active AI-detected fault investigation for this asset.'),
    ).not.toBeInTheDocument()
  })

  it('keeps a previously-loaded investigation visible when a background refresh fails', () => {
    // Regression: React Query keeps `data` populated across a failed
    // background refetch, so `investigation` and `error` can both be
    // truthy at once — the last-good diagnosis must stay on screen.
    render(
      <ActiveFaultInvestigationCard
        {...defaultProps}
        investigation={baseInvestigation}
        loading={false}
        error="Refresh failed: network error"
      />,
    )

    expect(screen.getByText('Refresh failed: network error')).toBeInTheDocument()
    expect(screen.getByText('cooling degradation')).toBeInTheDocument()
    expect(screen.getByText('Inspect cooling subsystem')).toBeInTheDocument()
  })

  it('shows a normal empty state (not an error) when there is no active investigation', () => {
    render(
      <ActiveFaultInvestigationCard {...defaultProps} investigation={null} loading={false} />,
    )

    expect(
      screen.getByText('No active AI-detected fault investigation for this asset.'),
    ).toBeInTheDocument()
  })

  it('renders the full information hierarchy for an active investigation', () => {
    render(
      <ActiveFaultInvestigationCard
        {...defaultProps}
        investigation={baseInvestigation}
        loading={false}
      />,
    )

    // Fault state
    expect(screen.getByText('cooling degradation')).toBeInTheDocument()
    // Corroboration
    expect(screen.getByText('corroborated')).toBeInTheDocument()
    expect(screen.getByText(baseInvestigation.corroboration_notes)).toBeInTheDocument()
    // Urgency
    expect(screen.getByText('ELEVATED')).toBeInTheDocument()
    // Recommendation
    expect(screen.getByText('Inspect cooling subsystem')).toBeInTheDocument()
    expect(screen.getByText('Check coolant pump')).toBeInTheDocument()
    // Authority boundary — always visible
    expect(screen.getByText(baseInvestigation.authority_boundary_note)).toBeInTheDocument()
    // Supporting evidence
    expect(screen.getByText('stack_temperature')).toBeInTheDocument()
  })

  it('renders the score with a caveat, never as a bare percentage', () => {
    render(
      <ActiveFaultInvestigationCard
        {...defaultProps}
        investigation={baseInvestigation}
        loading={false}
      />,
    )

    expect(screen.getByText('Diagnostic model score: 0.87')).toBeInTheDocument()
    expect(
      screen.getByText(baseInvestigation.provenance!.score_semantics),
    ).toBeInTheDocument()
    expect(screen.queryByText(/87%/)).not.toBeInTheDocument()
    expect(screen.queryByText(/chance of/i)).not.toBeInTheDocument()
  })

  it('keeps model and provenance details collapsed by default', () => {
    const { container } = render(
      <ActiveFaultInvestigationCard
        {...defaultProps}
        investigation={baseInvestigation}
        loading={false}
      />,
    )

    const details = container.querySelector('details')
    expect(details).not.toBeNull()
    expect(details?.open).toBe(false)
  })

  it('explains a withheld recommendation using the backend-provided reason', () => {
    const withheld: FaultInvestigationSummaryResponse = {
      ...baseInvestigation,
      corroboration_result: 'not_corroborated',
      urgency: 'INFORMATIONAL',
      recommendation_status: 'withheld',
      recommendation: {
        id: 'rec-2',
        status: 'withheld',
        category: 'monitor',
        urgency: 'INFORMATIONAL',
        action_summary: 'No fault-action recommendation at this time',
        reason:
          'The model alert was recorded, but deterministic telemetry checks did not support a fault-action recommendation.',
        recommended_steps: [],
        limitations: 'Automated inspection cannot substitute for a manual check.',
      },
    }

    render(
      <ActiveFaultInvestigationCard {...defaultProps} investigation={withheld} loading={false} />,
    )

    expect(screen.getByText('Recommendation withheld')).toBeInTheDocument()
    expect(
      screen.getByText(
        'The model alert was recorded, but deterministic telemetry checks did not support a fault-action recommendation.',
      ),
    ).toBeInTheDocument()
  })

  it('explains a cleared investigation with no recommendation', () => {
    const cleared: FaultInvestigationSummaryResponse = {
      ...baseInvestigation,
      investigation_status: 'CLEARED',
      alert_transition_type: 'cleared',
      corroboration_result: 'not_applicable',
      urgency: null,
      recommendation_status: null,
      recommendation: null,
    }

    render(
      <ActiveFaultInvestigationCard {...defaultProps} investigation={cleared} loading={false} />,
    )

    expect(
      screen.getByText('This fault has been cleared; no active recommendation.'),
    ).toBeInTheDocument()
  })
})
