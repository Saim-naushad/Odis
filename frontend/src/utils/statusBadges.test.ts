import { describe, expect, it } from 'vitest'
import { corroborationResultVariant, faultUrgencyVariant } from './statusBadges'

describe('faultUrgencyVariant', () => {
  it.each([
    ['URGENT', 'danger'],
    ['ELEVATED', 'warn'],
    ['INSPECTION_REQUIRED', 'info'],
    ['INFORMATIONAL', 'neutral'],
    ['SOMETHING_UNKNOWN', 'neutral'],
  ] as const)('maps %s to %s', (urgency, expected) => {
    expect(faultUrgencyVariant(urgency)).toBe(expected)
  })
})

describe('corroborationResultVariant', () => {
  it.each([
    ['corroborated', 'warn'],
    ['partially_corroborated', 'info'],
    ['not_corroborated', 'neutral'],
    ['insufficient_evidence', 'neutral'],
    ['not_applicable', 'neutral'],
    ['something_unknown', 'neutral'],
  ] as const)('maps %s to %s', (result, expected) => {
    expect(corroborationResultVariant(result)).toBe(expected)
  })

  it('never maps corroborated to danger, even at full agreement', () => {
    // Urgency carries the alarm signal, not corroboration strength — a
    // model-detected-only fault must never render as red "critical" solely
    // because deterministic telemetry agreed with it.
    expect(corroborationResultVariant('corroborated')).not.toBe('danger')
  })
})
