export type BadgeVariant = 'neutral' | 'info' | 'warn' | 'danger'

export function priorityVariant(priority: string): BadgeVariant {
  if (priority === 'P0') return 'danger'
  if (priority === 'P1') return 'warn'
  if (priority === 'P2') return 'info'
  return 'neutral'
}

export function severityVariant(severity: string): BadgeVariant {
  if (severity === 'CRITICAL') return 'danger'
  if (severity === 'WARNING') return 'warn'
  if (severity === 'INFO') return 'info'
  return 'neutral'
}

export function notificationStatusVariant(status: string): BadgeVariant {
  if (status === 'OPEN') return 'warn'
  if (status === 'ACKNOWLEDGED') return 'info'
  if (status === 'RESOLVED') return 'neutral'
  return 'neutral'
}

/** Status of an operator's response to a recommendation ('NEW' = no
 * transition recorded yet). */
export function investigationStatusVariant(status: string): BadgeVariant {
  if (status === 'ACKNOWLEDGED') return 'warn'
  if (status === 'INVESTIGATING') return 'info'
  if (status === 'RESOLVED') return 'neutral'
  return 'neutral' // NEW
}

export function riskBadgeClass(riskLevel: string): string {
  switch (riskLevel) {
    case 'HIGH':
      return 'status-badge-critical'
    case 'MEDIUM':
      return 'status-badge-warning'
    case 'LOW':
      return 'status-badge-normal'
    default:
      return 'status-badge-info'
  }
}

export function semanticBadgeClass(variant: BadgeVariant): string {
  switch (variant) {
    case 'danger':
      return 'status-badge-critical'
    case 'warn':
      return 'status-badge-warning'
    case 'info':
      return 'status-badge-info'
    default:
      return 'status-badge-info'
  }
}
