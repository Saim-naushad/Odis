import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import type { ReactElement } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ActionPlaybook } from './ActionPlaybook'
import { OPERATORS } from '../../utils/operators'
import type {
  InvestigationTransitionResponse,
  RecommendationResponse,
} from '../../types/monitoring'

const recommendMockRecordTransition = vi.fn()

vi.mock('../../api/monitoringClient', () => ({
  monitoringClient: {
    recordInvestigationTransition: (...args: unknown[]) =>
      recommendMockRecordTransition(...args),
  },
}))

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

function renderWithClient(ui: ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>,
  )
}

describe('ActionPlaybook', () => {
  afterEach(() => {
    cleanup()
    recommendMockRecordTransition.mockReset()
    localStorage.clear()
  })

  it('renders recommendation steps once', () => {
    renderWithClient(
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
  })

  it('shows NEW status and an Acknowledge action when no investigation exists', () => {
    renderWithClient(
      <ActionPlaybook
        selectedAssetId="fc-stack-01"
        recommendation={recommendation}
        investigation={null}
        loading={false}
      />,
    )

    expect(screen.getByText('NEW')).toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: 'Acknowledge' }),
    ).toBeInTheDocument()
    expect(
      screen.queryByRole('button', { name: 'Start investigating' }),
    ).not.toBeInTheDocument()
  })

  it('defaults to the first operator persona and records the transition against it', async () => {
    const transitionResponse: InvestigationTransitionResponse = {
      id: 'inv-1',
      asset_id: 'fc-stack-01',
      recommendation_id: 'rec-1',
      status: 'ACKNOWLEDGED',
      actor_id: OPERATORS[0].id,
      actor_display_name: OPERATORS[0].displayName,
      occurred_at: '2026-01-01T10:05:00Z',
      notes: null,
    }
    recommendMockRecordTransition.mockResolvedValue(transitionResponse)

    renderWithClient(
      <ActionPlaybook
        selectedAssetId="fc-stack-01"
        recommendation={recommendation}
        investigation={null}
        loading={false}
      />,
    )

    // No free-text identity required — a persona is preselected, so the
    // action is available immediately.
    const button = screen.getByRole('button', { name: 'Acknowledge' })
    expect(button).not.toBeDisabled()
    fireEvent.click(button)

    await waitFor(() => {
      expect(recommendMockRecordTransition).toHaveBeenCalledWith('fc-stack-01', {
        recommendation_id: 'rec-1',
        status: 'ACKNOWLEDGED',
        actor_id: OPERATORS[0].id,
        actor_display_name: `${OPERATORS[0].displayName} — ${OPERATORS[0].role}`,
        notes: undefined,
      })
    })
  })

  it('records the transition against whichever operator persona is selected', async () => {
    const secondOperator = OPERATORS[1]
    recommendMockRecordTransition.mockResolvedValue({
      id: 'inv-1',
      asset_id: 'fc-stack-01',
      recommendation_id: 'rec-1',
      status: 'ACKNOWLEDGED',
      actor_id: secondOperator.id,
      actor_display_name: secondOperator.displayName,
      occurred_at: '2026-01-01T10:05:00Z',
      notes: null,
    } satisfies InvestigationTransitionResponse)

    renderWithClient(
      <ActionPlaybook
        selectedAssetId="fc-stack-01"
        recommendation={recommendation}
        investigation={null}
        loading={false}
      />,
    )

    fireEvent.click(
      screen.getByRole('radio', { name: new RegExp(secondOperator.displayName) }),
    )
    fireEvent.click(screen.getByRole('button', { name: 'Acknowledge' }))

    await waitFor(() => {
      expect(recommendMockRecordTransition).toHaveBeenCalledWith('fc-stack-01', {
        recommendation_id: 'rec-1',
        status: 'ACKNOWLEDGED',
        actor_id: secondOperator.id,
        actor_display_name: `${secondOperator.displayName} — ${secondOperator.role}`,
        notes: undefined,
      })
    })
  })

  it('does not show a "recommendation changed" notice on first render', () => {
    renderWithClient(
      <ActionPlaybook
        selectedAssetId="fc-stack-01"
        recommendation={recommendation}
        investigation={null}
        loading={false}
      />,
    )

    expect(screen.queryByRole('status')).not.toBeInTheDocument()
  })

  it('shows a "recommendation changed" notice when a different recommendation id replaces the current one', () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    })
    const { rerender } = render(
      <QueryClientProvider client={queryClient}>
        <ActionPlaybook
          selectedAssetId="fc-stack-01"
          recommendation={recommendation}
          investigation={null}
          loading={false}
        />
      </QueryClientProvider>,
    )
    expect(screen.queryByRole('status')).not.toBeInTheDocument()

    const changedRecommendation: RecommendationResponse = {
      ...recommendation,
      id: 'rec-2',
      priority: 'P3',
      title: 'Continue monitoring',
    }
    rerender(
      <QueryClientProvider client={queryClient}>
        <ActionPlaybook
          selectedAssetId="fc-stack-01"
          recommendation={changedRecommendation}
          investigation={null}
          loading={false}
        />
      </QueryClientProvider>,
    )

    expect(screen.getByRole('status')).toHaveTextContent(/Recommendation changed/)
  })

  it('does not show a "recommendation changed" notice when the same recommendation id re-renders', () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    })
    const { rerender } = render(
      <QueryClientProvider client={queryClient}>
        <ActionPlaybook
          selectedAssetId="fc-stack-01"
          recommendation={recommendation}
          investigation={null}
          loading={false}
        />
      </QueryClientProvider>,
    )

    rerender(
      <QueryClientProvider client={queryClient}>
        <ActionPlaybook
          selectedAssetId="fc-stack-01"
          recommendation={{ ...recommendation }}
          investigation={null}
          loading={false}
        />
      </QueryClientProvider>,
    )

    expect(screen.queryByRole('status')).not.toBeInTheDocument()
  })

  it('shows no actions once resolved', () => {
    const resolved: InvestigationTransitionResponse = {
      id: 'inv-2',
      asset_id: 'fc-stack-01',
      recommendation_id: 'rec-1',
      status: 'RESOLVED',
      actor_id: 'j.operator',
      actor_display_name: 'j.operator',
      occurred_at: '2026-01-01T11:00:00Z',
      notes: null,
    }

    renderWithClient(
      <ActionPlaybook
        selectedAssetId="fc-stack-01"
        recommendation={recommendation}
        investigation={resolved}
        loading={false}
      />,
    )

    expect(screen.getByText('RESOLVED')).toBeInTheDocument()
    expect(screen.getByText('This investigation is resolved.')).toBeInTheDocument()
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })
})
