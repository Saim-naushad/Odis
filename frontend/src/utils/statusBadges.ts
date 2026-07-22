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

/**
 * AI-fault urgency ("how alarmed should the operator be"). Distinct axis
 * from `corroborationResultVariant` ("how much did deterministic telemetry
 * agree with the model") — the two must not share one mapping function.
 * `URGENT` is not produced by the current recommendation policy, but is
 * mapped for forward-compat since the backend Literal already allows it.
 */
export function faultUrgencyVariant(urgency: string): BadgeVariant {
  if (urgency === 'URGENT') return 'danger'
  if (urgency === 'ELEVATED') return 'warn'
  if (urgency === 'INSPECTION_REQUIRED') return 'info'
  return 'neutral' // INFORMATIONAL
}

/**
 * Deterministic corroboration strength. Intentionally caps at 'warn' even
 * at full agreement ('corroborated') — this fault was only ever detected
 * by a diagnostic model, so the urgency badge (`faultUrgencyVariant`)
 * carries the alarm signal, not this one; a red "critical" treatment here
 * would overstate what corroboration alone establishes.
 */
export function corroborationResultVariant(result: string): BadgeVariant {
  if (result === 'corroborated') return 'warn'
  if (result === 'partially_corroborated') return 'info'
  return 'neutral' // not_corroborated | insufficient_evidence | not_applicable
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
