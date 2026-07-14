import type { NotificationResponse } from '../../types/monitoring'
import {
  notificationStatusVariant,
  semanticBadgeClass,
  severityVariant,
} from '../../utils/statusBadges'

interface ActiveAlertBannerProps {
  notification: NotificationResponse
}

function severityBorderColor(severity: string): string {
  switch (severity) {
    case 'CRITICAL':
      return 'var(--status-critical)'
    case 'WARNING':
      return 'var(--status-warning)'
    default:
      return 'var(--status-info)'
  }
}

// Deliberately terse: the full description already lives in the Action
// Playbook below, so this banner only needs to say "there is an active
// alert" — repeating the same paragraph here reads as duplicated content.
export function ActiveAlertBanner({ notification }: ActiveAlertBannerProps) {
  return (
    <section
      className="flex flex-wrap items-center gap-3 border-b px-6 py-3"
      style={{
        borderColor: 'var(--surface-border)',
        borderLeftWidth: '4px',
        borderLeftColor: severityBorderColor(notification.severity),
        background: 'var(--surface-base)',
      }}
      aria-label="Active alert"
      role="alert"
    >
      <span
        className={`status-badge ${semanticBadgeClass(severityVariant(notification.severity))}`}
      >
        {notification.severity}
      </span>
      <span
        className={`status-badge ${semanticBadgeClass(notificationStatusVariant(notification.status))}`}
      >
        {notification.status}
      </span>
      <p
        className="min-w-0 flex-1 truncate text-sm font-semibold"
        style={{ color: 'var(--text-primary)' }}
      >
        {notification.title}
      </p>
      <span className="text-[10px] shrink-0" style={{ color: 'var(--text-muted)' }}>
        {new Date(notification.created_at).toLocaleString()}
      </span>
    </section>
  )
}
