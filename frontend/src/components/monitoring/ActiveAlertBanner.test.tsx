import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { ActiveAlertBanner } from './ActiveAlertBanner'
import type { NotificationResponse } from '../../types/monitoring'

// No global test-cleanup hook is registered in src/test/setup.ts, so
// multiple renders within this file accumulate in the DOM unless each test
// file cleans up after itself.
afterEach(cleanup)

const notification: NotificationResponse = {
  id: 'notif-1',
  asset_id: 'fc-stack-01',
  recommendation_id: 'rec-1',
  severity: 'WARNING',
  status: 'OPEN',
  title: 'Stack temperature deviation',
  message: 'Cooling flow may be insufficient.',
  created_at: '2026-01-01T10:00:00Z',
}

describe('ActiveAlertBanner', () => {
  it('renders a terse alert strip with severity, status, and title', () => {
    render(<ActiveAlertBanner notification={notification} />)

    expect(screen.getByRole('alert')).toBeInTheDocument()
    expect(screen.getByText('Stack temperature deviation')).toBeInTheDocument()
    expect(screen.getByText('WARNING')).toBeInTheDocument()
    expect(screen.getByText('OPEN')).toBeInTheDocument()
  })

  it('does not repeat the full message (that detail lives in the Action Playbook)', () => {
    render(<ActiveAlertBanner notification={notification} />)

    expect(
      screen.queryByText('Cooling flow may be insufficient.'),
    ).not.toBeInTheDocument()
  })

  it('does not show a mismatch note when current health status is unknown', () => {
    render(<ActiveAlertBanner notification={notification} />)

    expect(screen.queryByText(/while conditions were more severe/)).not.toBeInTheDocument()
  })

  it('does not show a mismatch note when severity matches current health status', () => {
    render(
      <ActiveAlertBanner notification={notification} currentHealthStatus="WARNING" />,
    )

    expect(screen.queryByText(/while conditions were more severe/)).not.toBeInTheDocument()
  })

  it('explains the distinction when a CRITICAL notification stays open after health recovers to NORMAL', () => {
    const critical: NotificationResponse = { ...notification, severity: 'CRITICAL' }
    render(<ActiveAlertBanner notification={critical} currentHealthStatus="NORMAL" />)

    expect(screen.getByText(/while conditions were more severe/)).toBeInTheDocument()
    expect(screen.getByText('NORMAL')).toBeInTheDocument()
  })

  it('explains the distinction when a WARNING notification stays open after health recovers to NORMAL', () => {
    render(<ActiveAlertBanner notification={notification} currentHealthStatus="NORMAL" />)

    expect(screen.getByText(/while conditions were more severe/)).toBeInTheDocument()
  })
})
