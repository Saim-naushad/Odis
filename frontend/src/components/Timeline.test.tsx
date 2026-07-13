import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { Timeline } from './Timeline'
import type { TimelineEventResponse } from '../types/monitoring'

afterEach(cleanup)

const sampleEvents: TimelineEventResponse[] = [
  {
    id: 'event-1',
    asset_id: 'asset-1',
    timestamp: '2026-01-01T10:00:00Z',
    event_type: 'observation_received',
    title: 'Observation received',
    description: 'New observation obs-1 recorded for the asset.',
    metadata: { observation_id: 'obs-1' },
  },
  {
    id: 'event-2',
    asset_id: 'asset-1',
    timestamp: '2026-01-01T10:05:00Z',
    event_type: 'reasoning_completed',
    title: 'Reasoning completed',
    description: 'Reasoning run run-1 finished for the asset.',
    metadata: { run_id: 'run-1' },
  },
]

describe('Timeline', () => {
  it('renders events with title, description, and timestamp', () => {
    render(<Timeline events={sampleEvents} loading={false} />)

    expect(screen.getByText('Timeline')).toBeInTheDocument()
    expect(screen.getByText('Observation received')).toBeInTheDocument()
    expect(
      screen.getByText('New observation obs-1 recorded for the asset.'),
    ).toBeInTheDocument()
    expect(screen.getByText('Reasoning completed')).toBeInTheDocument()
  })

  it('highlights the newest event', () => {
    const { container } = render(
      <Timeline events={sampleEvents} loading={false} />,
    )

    const highlighted = container.querySelector('.border-l-slate-400')
    expect(highlighted).not.toBeNull()
    expect(highlighted?.textContent).toContain('Reasoning completed')
  })

  it('shows empty state when no events are available', () => {
    render(<Timeline events={[]} loading={false} />)

    expect(
      screen.getByText('No operational events recorded for this asset yet.'),
    ).toBeInTheDocument()
  })

  it('invokes onSelectEvent with the full event when a run-linked row is clicked', () => {
    const onSelectEvent = vi.fn()
    render(
      <Timeline
        events={sampleEvents}
        loading={false}
        onSelectEvent={onSelectEvent}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: /Reasoning completed/i }))

    expect(onSelectEvent).toHaveBeenCalledWith(sampleEvents[1])
  })

  it('does not render a clickable row for events without a run_id', () => {
    const onSelectEvent = vi.fn()
    render(
      <Timeline
        events={sampleEvents}
        loading={false}
        onSelectEvent={onSelectEvent}
      />,
    )

    expect(
      screen.queryByRole('button', { name: /Observation received/i }),
    ).not.toBeInTheDocument()
  })

  it('highlights exactly the selected event, not just the newest', () => {
    const { container } = render(
      <Timeline
        events={sampleEvents}
        loading={false}
        selectedEventId="event-1"
        onSelectEvent={vi.fn()}
      />,
    )

    const highlighted = container.querySelector('.border-l-slate-400')
    expect(highlighted).not.toBeNull()
    expect(highlighted?.textContent).toContain('Observation received')
  })
})
