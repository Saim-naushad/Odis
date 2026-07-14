import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { ProductHeader } from './ProductHeader'

describe('ProductHeader', () => {
  afterEach(() => {
    cleanup()
  })
  it('renders LIVE as primary status and demotes a platform error', () => {
    render(
      <ProductHeader
        platformName="ODIS Platform"
        platformStatus="error"
        sseConnectionState="connected"
        lastUpdatedAt={new Date('2026-01-01T10:00:00Z')}
      />,
    )

    expect(screen.getByRole('heading', { name: 'ODIS' })).toBeInTheDocument()
    expect(screen.getByText('Live')).toBeInTheDocument()
    expect(screen.getByText('Platform unavailable')).toBeInTheDocument()
    expect(screen.queryByText(/Monitoring Console/i)).not.toBeInTheDocument()
  })

  it('distinguishes a non-critical degraded dependency from a platform error', () => {
    render(
      <ProductHeader
        platformStatus="degraded"
        sseConnectionState="connected"
      />,
    )

    expect(
      screen.getByText('Platform degraded (non-critical dependency)'),
    ).toBeInTheDocument()
    expect(screen.queryByText('Platform unavailable')).not.toBeInTheDocument()
  })

  it('hides platform label when healthy', () => {
    render(
      <ProductHeader
        platformStatus="ok"
        sseConnectionState="connected"
      />,
    )

    expect(screen.getByText('Live')).toBeInTheDocument()
    expect(screen.queryByText('Platform healthy')).not.toBeInTheDocument()
  })
})
