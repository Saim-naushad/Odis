import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { Timeline } from './Timeline'
import type { TimelineEventResponse } from '../types/monitoring'

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

    const highlighted = container.querySelector('.border-sky-500')
    expect(highlighted).not.toBeNull()
    expect(highlighted?.textContent).toContain('Reasoning completed')
  })

  it('shows empty state when no events are available', () => {
    render(<Timeline events={[]} loading={false} />)

    expect(
      screen.getByText('No operational events recorded for this asset yet.'),
    ).toBeInTheDocument()
  })
})
