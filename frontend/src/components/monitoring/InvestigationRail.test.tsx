import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { InvestigationRail } from './InvestigationRail'

const events = [
  {
    id: 'evt-1',
    asset_id: 'fc-stack-01',
    timestamp: '2026-01-01T10:00:00Z',
    event_type: 'reasoning_completed' as const,
    title: 'Reasoning completed',
    description: 'Assessment finished.',
    metadata: {},
  },
]

describe('InvestigationRail', () => {
  it('renders toolbox sections and expert entry point', () => {
    const onOpenExpert = vi.fn()

    render(
      <InvestigationRail
        events={events}
        loading={false}
        onOpenExpert={onOpenExpert}
        expertDisabled={false}
      />,
    )

    expect(screen.getByLabelText('Investigation')).toBeInTheDocument()
    expect(screen.getByText('Event context')).toBeInTheDocument()
    expect(screen.getByText('Diagnostics')).toBeInTheDocument()
    expect(screen.getByText('Reasoning completed')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /Open reasoning runs/i }))
    expect(onOpenExpert).toHaveBeenCalled()
  })
})
