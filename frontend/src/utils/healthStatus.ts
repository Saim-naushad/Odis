export type HealthStatusKind = 'NORMAL' | 'WARNING' | 'CRITICAL' | string

export function healthStatusBadgeClass(status: HealthStatusKind): string {
  switch (status) {
    case 'CRITICAL':
      return 'status-badge-critical'
    case 'WARNING':
      return 'status-badge-warning'
    case 'NORMAL':
      return 'status-badge-normal'
    default:
      return 'status-badge-info'
  }
}

export function healthStatusDotClass(status: HealthStatusKind): string {
  switch (status) {
    case 'CRITICAL':
      return 'status-dot-critical'
    case 'WARNING':
      return 'status-dot-warning'
    case 'NORMAL':
      return 'status-dot-normal'
    default:
      return 'status-dot-muted'
  }
}
