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

export function ActiveAlertBanner({ notification }: ActiveAlertBannerProps) {
  return (
    <section
      className="border-b px-6 py-3"
      style={{
        borderColor: 'var(--surface-border)',
        borderLeftWidth: '4px',
        borderLeftColor: severityBorderColor(notification.severity),
        background: 'var(--surface-base)',
      }}
      aria-label="Active alert"
      role="alert"
    >
      <div className="flex flex-wrap items-center gap-2">
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
        <span className="text-[10px]" style={{ color: 'var(--text-muted)' }}>
          {new Date(notification.created_at).toLocaleString()}
        </span>
      </div>

      <p className="mt-2 text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
        {notification.title}
      </p>
      <p className="mt-1 text-xs leading-relaxed" style={{ color: 'var(--text-secondary)' }}>
        {notification.message}
      </p>
    </section>
  )
}
