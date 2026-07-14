import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { ActiveAlertBanner } from './ActiveAlertBanner'
import type { NotificationResponse } from '../../types/monitoring'

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
})
