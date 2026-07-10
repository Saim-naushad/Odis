import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { SystemFooter } from './SystemFooter'

describe('SystemFooter', () => {
  afterEach(() => {
    cleanup()
  })

  it('shows SSE state and demoted platform metadata', () => {
    render(
      <SystemFooter
        sseConnectionState="connected"
        lastUpdatedAt={new Date('2026-01-01T10:00:00Z')}
        reasoningEngineVersion="1.2.3"
        platformPhase="dev"
      />,
    )

    expect(screen.getByText('SSE connected')).toBeInTheDocument()
    expect(screen.getByText(/Engine 1.2.3/)).toBeInTheDocument()
    expect(screen.getByText(/Phase dev/)).toBeInTheDocument()
    expect(screen.getByText(/Last sync/)).toBeInTheDocument()
  })

  it('falls back to ODIS when no platform metadata', () => {
    render(<SystemFooter sseConnectionState="disconnected" />)

    expect(screen.getByText('ODIS')).toBeInTheDocument()
    expect(screen.getByText('SSE offline')).toBeInTheDocument()
  })
})
