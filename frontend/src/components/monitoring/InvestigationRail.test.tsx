import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import type { ReactElement } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { InvestigationRail } from './InvestigationRail'
import type {
  FaultInvestigationDetailResponse,
  MonitoringRunDetailsResponse,
  TimelineEventResponse,
} from '../../types/monitoring'

afterEach(cleanup)

const mockGetFaultInvestigationDetail = vi.fn()

vi.mock('../../api/monitoringClient', () => ({
  monitoringClient: {
    getFaultInvestigationDetail: (...args: unknown[]) =>
      mockGetFaultInvestigationDetail(...args),
  },
}))

function renderWithClient(ui: ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>)
}

const events: TimelineEventResponse[] = [
  {
    id: 'evt-1',
    asset_id: 'fc-stack-01',
    timestamp: '2026-01-01T09:55:00Z',
    event_type: 'observation_received',
    title: 'Observation received',
    description: 'New observation obs-1 recorded for the asset.',
    metadata: { observation_id: 'obs-1' },
  },
  {
    id: 'evt-2',
    asset_id: 'fc-stack-01',
    timestamp: '2026-01-01T10:00:00Z',
    event_type: 'reasoning_completed',
    title: 'Reasoning completed',
    description: 'Assessment finished.',
    metadata: { run_id: 'run-1' },
  },
]

const runDetails: MonitoringRunDetailsResponse = {
  run_id: 'run-1',
  started_at: '2026-01-01T10:00:00Z',
  observations: [],
  reasoning_trace: null,
  structured_assessment: null,
  operational_situation: {
    id: 'sit-1',
    goal_id: 'goal-1',
    observation_ids: [],
    assessment: 'Stack temperature is trending upward but within limits.',
  },
  decision_context: {
    id: 'ctx-1',
    goal_id: 'goal-1',
    situation_id: 'sit-1',
    assessment: 'Stack temperature is trending upward but within limits.',
    created_at: '2026-01-01T10:00:00Z',
  },
  decision_plan: {
    id: 'plan-1',
    priority: 'P2',
    recommendation: 'Monitor cooling loop over the next cycle.',
    context_id: 'ctx-1',
    created_at: '2026-01-01T10:00:00Z',
    justification: 'Trend is mild and within tolerance.',
    confidence: { value: 82, rationale: 'Consistent readings across sensors.' },
    evidence: [
      {
        id: 'ev-1',
        description: 'Stack temperature rising',
        measurement_type: 'temperature',
        observed_value: '58C',
        contribution_weight: 0.6,
      },
    ],
    alternative_hypotheses: [
      { title: 'Sensor drift', reason: 'Single sensor outlier', confidence: 15 },
    ],
  },
}

function baseProps() {
  return {
    events,
    loading: false,
    onOpenExpert: vi.fn(),
    expertDisabled: false,
    onSelectRun: vi.fn(),
    runDetailsLoading: false,
  }
}

describe('InvestigationRail', () => {
  it('renders toolbox sections and expert entry point', () => {
    const props = baseProps()

    renderWithClient(<InvestigationRail {...props} />)

    expect(screen.getByLabelText('Investigation')).toBeInTheDocument()
    expect(screen.getByText('Event context')).toBeInTheDocument()
    expect(screen.getByText('Diagnostics')).toBeInTheDocument()
    expect(screen.getByText('Reasoning completed')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /Open reasoning runs/i }))
    expect(props.onOpenExpert).toHaveBeenCalled()
  })

  it('shows the placeholder when nothing is selected yet', () => {
    renderWithClient(<InvestigationRail {...baseProps()} />)

    expect(
      screen.getByText(
        'Select a timeline event to inspect context and correlate with telemetry.',
      ),
    ).toBeInTheDocument()
  })

  it('defaults to the newest event for the currently selected run', () => {
    renderWithClient(
      <InvestigationRail
        {...baseProps()}
        selectedRunId="run-1"
        runDetails={runDetails}
      />,
    )

    expect(screen.getAllByText('Assessment finished.')).toHaveLength(2)
    expect(
      screen.getByText('Monitor cooling loop over the next cycle.'),
    ).toBeInTheDocument()
  })

  it('selects the exact clicked event and calls onSelectRun with its run_id', () => {
    const props = baseProps()

    renderWithClient(<InvestigationRail {...props} />)

    fireEvent.click(screen.getByRole('button', { name: /Reasoning completed/i }))

    expect(props.onSelectRun).toHaveBeenCalledWith('run-1')
    // Description now renders both in the timeline row and the Event panel.
    expect(screen.getAllByText('Assessment finished.')).toHaveLength(2)
  })

  it('does not offer a click target for events without a run_id', () => {
    const props = baseProps()

    renderWithClient(<InvestigationRail {...props} />)

    expect(
      screen.queryByRole('button', { name: /Observation received/i }),
    ).not.toBeInTheDocument()
  })

  it('renders evidence, confidence, and alternative hypotheses for the associated run', () => {
    renderWithClient(
      <InvestigationRail
        {...baseProps()}
        selectedRunId="run-1"
        runDetails={runDetails}
      />,
    )

    expect(
      screen.getByText('Stack temperature is trending upward but within limits.'),
    ).toBeInTheDocument()
    expect(screen.getByText('Confidence: 82/100')).toBeInTheDocument()
    expect(screen.getByText(/Stack temperature rising/)).toBeInTheDocument()
    expect(screen.getByText(/Sensor drift/)).toBeInTheDocument()
  })

  it('shows a loading state while the reasoning run is being fetched', () => {
    renderWithClient(
      <InvestigationRail
        {...baseProps()}
        selectedRunId="run-1"
        runDetailsLoading
      />,
    )

    expect(screen.getByText('Loading reasoning context…')).toBeInTheDocument()
  })

  it('shows an error state with a retry action', () => {
    const onRetryRunDetails = vi.fn()

    renderWithClient(
      <InvestigationRail
        {...baseProps()}
        selectedRunId="run-1"
        runDetailsError="Failed to load run details"
        onRetryRunDetails={onRetryRunDetails}
      />,
    )

    expect(screen.getByText('Failed to load run details')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Retry/i }))
    expect(onRetryRunDetails).toHaveBeenCalled()
  })

  describe('AI-fault timeline events (Issue 3 regression)', () => {
    const aiFaultEvent: TimelineEventResponse = {
      id: 'evt-ai-1',
      asset_id: 'fc-stack-01',
      timestamp: '2026-01-01T10:10:00Z',
      event_type: 'ai_fault_corroboration_completed',
      title: 'Deterministic corroboration: partially_corroborated',
      description: 'stack_temperature is increasing while coolant_flow is stable.',
      metadata: { investigation_id: 'inv-1', corroboration_result: 'partially_corroborated' },
    }

    const investigationDetail: FaultInvestigationDetailResponse = {
      investigation_id: 'inv-1',
      asset_id: 'fc-stack-01',
      current: {
        investigation_id: 'inv-1',
        asset_id: 'fc-stack-01',
        investigation_status: 'OPEN',
        diagnosed_fault_class: 'cooling_degradation',
        previous_diagnosed_fault_class: null,
        alert_transition_type: 'confirmed',
        observed_at: '2026-01-01T10:10:00Z',
        corroboration_result: 'partially_corroborated',
        corroboration_notes:
          'stack_temperature is increasing while coolant_flow is stable.',
        corroboration_rule_ids: ['cooling_degradation.stack_temperature_increasing'],
        urgency: 'INSPECTION_REQUIRED',
        recommendation_status: 'produced',
        recommendation: {
          id: 'ai-fault-rec-1',
          status: 'produced',
          category: 'investigate',
          urgency: 'INSPECTION_REQUIRED',
          action_summary: 'Verify cooling loop before acting.',
          reason: 'Evidence partially supports the diagnosis.',
          recommended_steps: ['Cross-check stack temperature against a secondary sensor.'],
          limitations: 'Evidence is ambiguous.',
        },
        authority_boundary_note:
          'This fault was detected by a diagnostic model and is evidence, not a confirmed diagnosis.',
        supporting_evidence: [],
        provenance: null,
      },
      timeline: [],
    }

    it('offers a click target for an ai_fault_* event carrying investigation_id', () => {
      mockGetFaultInvestigationDetail.mockResolvedValue(investigationDetail)
      const props = { ...baseProps(), events: [...events, aiFaultEvent] }

      renderWithClient(<InvestigationRail {...props} />)

      expect(
        screen.getByRole('button', { name: /Deterministic corroboration/i }),
      ).toBeInTheDocument()
    })

    it('renders real AI fault investigation detail in Event Context when selected', async () => {
      mockGetFaultInvestigationDetail.mockResolvedValue(investigationDetail)
      const props = { ...baseProps(), events: [...events, aiFaultEvent] }

      renderWithClient(<InvestigationRail {...props} />)
      fireEvent.click(
        screen.getByRole('button', { name: /Deterministic corroboration/i }),
      )

      expect(await screen.findByText('Associated AI fault investigation')).toBeInTheDocument()
      expect(
        await screen.findByText(/cooling degradation.*confirmed/i),
      ).toBeInTheDocument()
      expect(
        screen.getByText('Verify cooling loop before acting.'),
      ).toBeInTheDocument()
      expect(mockGetFaultInvestigationDetail).toHaveBeenCalledWith(
        'inv-1',
        expect.anything(),
      )
      // Never leaves Event Context on the generic/blank placeholder.
      expect(
        screen.queryByText(
          'Select a timeline event to inspect context and correlate with telemetry.',
        ),
      ).not.toBeInTheDocument()
    })

    it('does not fabricate a reasoning-run relationship for an ai_fault_* event', async () => {
      mockGetFaultInvestigationDetail.mockResolvedValue(investigationDetail)
      const props = { ...baseProps(), events: [...events, aiFaultEvent] }

      renderWithClient(<InvestigationRail {...props} />)
      fireEvent.click(
        screen.getByRole('button', { name: /Deterministic corroboration/i }),
      )

      await waitFor(() =>
        expect(screen.getByText('Associated AI fault investigation')).toBeInTheDocument(),
      )
      expect(screen.queryByText('Associated reasoning run')).not.toBeInTheDocument()
      expect(props.onSelectRun).not.toHaveBeenCalled()
    })
  })
})
