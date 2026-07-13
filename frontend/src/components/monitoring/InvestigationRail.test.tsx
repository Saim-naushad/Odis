import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { InvestigationRail } from './InvestigationRail'
import type {
  MonitoringRunDetailsResponse,
  TimelineEventResponse,
} from '../../types/monitoring'

afterEach(cleanup)

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

    render(<InvestigationRail {...props} />)

    expect(screen.getByLabelText('Investigation')).toBeInTheDocument()
    expect(screen.getByText('Event context')).toBeInTheDocument()
    expect(screen.getByText('Diagnostics')).toBeInTheDocument()
    expect(screen.getByText('Reasoning completed')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /Open reasoning runs/i }))
    expect(props.onOpenExpert).toHaveBeenCalled()
  })

  it('shows the placeholder when nothing is selected yet', () => {
    render(<InvestigationRail {...baseProps()} />)

    expect(
      screen.getByText(
        'Select a timeline event to inspect context and correlate with telemetry.',
      ),
    ).toBeInTheDocument()
  })

  it('defaults to the newest event for the currently selected run', () => {
    render(
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

    render(<InvestigationRail {...props} />)

    fireEvent.click(screen.getByRole('button', { name: /Reasoning completed/i }))

    expect(props.onSelectRun).toHaveBeenCalledWith('run-1')
    // Description now renders both in the timeline row and the Event panel.
    expect(screen.getAllByText('Assessment finished.')).toHaveLength(2)
  })

  it('does not offer a click target for events without a run_id', () => {
    const props = baseProps()

    render(<InvestigationRail {...props} />)

    expect(
      screen.queryByRole('button', { name: /Observation received/i }),
    ).not.toBeInTheDocument()
  })

  it('renders evidence, confidence, and alternative hypotheses for the associated run', () => {
    render(
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
    render(
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

    render(
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
})
