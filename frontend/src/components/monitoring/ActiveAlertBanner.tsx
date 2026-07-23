import type { NotificationResponse } from '../../types/monitoring'
import {
  notificationStatusVariant,
  semanticBadgeClass,
  severityVariant,
} from '../../utils/statusBadges'

interface ActiveAlertBannerProps {
  notification: NotificationResponse
  currentHealthStatus?: string
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

// Notifications are an append-only log of when a severity threshold was
// crossed - they do not auto-clear when health recovers (see
// docs/platform/demo-environment.md's Known Limitations). That means this
// banner can legitimately still show an OPEN CRITICAL/WARNING notification
// while the asset's live health has since recovered. Rather than let that
// read as a contradiction ("currently normal" + "immediate mitigation
// required" with no explanation), flag the mismatch explicitly whenever the
// notification's severity implies worse than the current health status.
function describesWorseThanCurrent(
  severity: string,
  currentHealthStatus?: string,
): boolean {
  if (!currentHealthStatus) return false
  if (severity === 'CRITICAL' && currentHealthStatus !== 'CRITICAL') return true
  if (severity === 'WARNING' && currentHealthStatus === 'NORMAL') return true
  return false
}

// Deliberately terse: the full description already lives in the Action
// Playbook below, so this banner only needs to say "there is an active
// alert" — repeating the same paragraph here reads as duplicated content.
export function ActiveAlertBanner({
  notification,
  currentHealthStatus,
}: ActiveAlertBannerProps) {
  const isStale = describesWorseThanCurrent(notification.severity, currentHealthStatus)

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
        className="min-w-0 flex-1 text-sm font-semibold sm:truncate"
        style={{ color: 'var(--text-primary)' }}
      >
        {notification.title}
      </p>
      <span className="basis-full text-[10px] shrink-0 sm:basis-auto" style={{ color: 'var(--text-muted)' }}>
        {new Date(notification.created_at).toLocaleString()}
      </span>
      {isStale && (
        <p
          className="basis-full text-xs"
          style={{ color: 'var(--text-muted)' }}
        >
          Raised at the timestamp above, while conditions were more severe.
          Current health status is now <strong>{currentHealthStatus}</strong> —
          this notification stays open until an operator resolves it or a new,
          more severe one supersedes it.
        </p>
      )}
    </section>
  )
}
