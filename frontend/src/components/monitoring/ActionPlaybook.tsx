import { useState } from 'react'
import type {
  InvestigationStatus,
  InvestigationTransitionResponse,
  RecommendationResponse,
} from '../../types/monitoring'
import {
  investigationStatusVariant,
  priorityVariant,
  semanticBadgeClass,
} from '../../utils/statusBadges'
import { useInvestigationTransition } from '../../hooks/useInvestigationTransition'
import { OPERATORS, useSelectedOperator } from '../../utils/operators'

interface ActionPlaybookProps {
  selectedAssetId?: string
  recommendation?: RecommendationResponse
  investigation?: InvestigationTransitionResponse | null
  loading: boolean
  error?: string
}

type CurrentStatus = 'NEW' | InvestigationStatus

const NEXT_TRANSITIONS: Record<
  CurrentStatus,
  { status: InvestigationStatus; label: string }[]
> = {
  NEW: [{ status: 'ACKNOWLEDGED', label: 'Acknowledge' }],
  ACKNOWLEDGED: [
    { status: 'INVESTIGATING', label: 'Start investigating' },
    { status: 'RESOLVED', label: 'Resolve' },
  ],
  INVESTIGATING: [{ status: 'RESOLVED', label: 'Resolve' }],
  RESOLVED: [],
}

function currentStatus(
  investigation?: InvestigationTransitionResponse | null,
): CurrentStatus {
  const status = investigation?.status
  if (status === 'ACKNOWLEDGED' || status === 'INVESTIGATING' || status === 'RESOLVED') {
    return status
  }
  return 'NEW'
}

function priorityAccentColor(priority: string): string {
  const variant = priorityVariant(priority)
  switch (variant) {
    case 'danger':
      return 'var(--status-critical)'
    case 'warn':
      return 'var(--status-warning)'
    case 'info':
      return 'var(--status-info)'
    default:
      return 'var(--surface-border)'
  }
}

export function ActionPlaybook({
  selectedAssetId,
  recommendation,
  investigation,
  error,
}: ActionPlaybookProps) {
  const hasRecommendation = Boolean(recommendation)
  const [operator, selectOperator] = useSelectedOperator()
  const [notes, setNotes] = useState('')
  const transition = useInvestigationTransition(selectedAssetId)
  const status = currentStatus(investigation)
  const nextTransitions = NEXT_TRANSITIONS[status]
  const canAct = Boolean(recommendation)

  function handleTransition(nextStatus: InvestigationStatus) {
    if (!recommendation || !canAct) return
    transition.mutate(
      {
        recommendation_id: recommendation.id,
        status: nextStatus,
        actor_id: operator.id,
        actor_display_name: `${operator.displayName} — ${operator.role}`,
        notes: notes.trim() ? notes.trim() : undefined,
      },
      {
        onSuccess: () => setNotes(''),
      },
    )
  }

  return (
    <section
      className="rounded border px-6 py-6"
      style={{
        borderColor: hasRecommendation
          ? priorityAccentColor(recommendation!.priority)
          : 'var(--surface-border)',
        borderLeftWidth: hasRecommendation ? '4px' : undefined,
        background: 'var(--surface-raised)',
        boxShadow: hasRecommendation
          ? '0 1px 0 rgb(148 163 184 / 0.08), 0 8px 24px rgb(2 6 23 / 0.35)'
          : undefined,
      }}
      aria-label="Recommended action"
    >
      <div className="flex items-center justify-between gap-2">
        <div>
          <h2
            className="text-xs font-semibold uppercase tracking-wide"
            style={{ color: 'var(--text-secondary)' }}
          >
            Recommended action
          </h2>
          {hasRecommendation && (
            <p className="mt-1 text-[10px]" style={{ color: 'var(--text-muted)' }}>
              Operator playbook — follow steps in order
            </p>
          )}
        </div>
      </div>

      {error ? (
        <p className="mt-4 text-sm" style={{ color: 'var(--status-warning)' }}>
          {error}
        </p>
      ) : recommendation ? (
        <div className="mt-5 space-y-5">
          <div className="flex flex-wrap items-center gap-2">
            <span
              className={`status-badge ${semanticBadgeClass(priorityVariant(recommendation.priority))}`}
            >
              {recommendation.priority} · {recommendation.urgency}
            </span>
            <span className="status-badge status-badge-info">{recommendation.category}</span>
            <span
              className={`status-badge ${semanticBadgeClass(investigationStatusVariant(status))}`}
            >
              {status}
            </span>
          </div>

          <div
            className="rounded border px-4 py-4"
            style={{
              borderColor: 'var(--surface-border)',
              background: 'var(--surface-base)',
            }}
          >
            <p
              className="text-[10px] font-semibold uppercase tracking-wide"
              style={{ color: 'var(--text-muted)' }}
            >
              Investigation
            </p>
            {investigation && (
              <p className="mt-2 text-xs" style={{ color: 'var(--text-secondary)' }}>
                {investigation.actor_display_name} marked this{' '}
                {investigation.status.toLowerCase()} at{' '}
                {new Date(investigation.occurred_at).toLocaleString()}
                {investigation.notes ? ` — ${investigation.notes}` : ''}
              </p>
            )}
            {nextTransitions.length > 0 ? (
              <div className="mt-3 space-y-2">
                <div className="flex flex-wrap items-center gap-2">
                  <span
                    className="text-[10px] uppercase tracking-wide"
                    style={{ color: 'var(--text-muted)' }}
                  >
                    Acting as
                  </span>
                  <div className="flex flex-wrap gap-1" role="radiogroup" aria-label="Operator">
                    {OPERATORS.map((candidate) => {
                      const isActive = candidate.id === operator.id
                      return (
                        <button
                          key={candidate.id}
                          type="button"
                          role="radio"
                          aria-checked={isActive}
                          onClick={() => selectOperator(candidate.id)}
                          className="rounded border px-2 py-1 text-[11px] font-medium transition-colors"
                          style={{
                            borderColor: isActive
                              ? 'var(--focus-ring)'
                              : 'var(--surface-border)',
                            background: isActive
                              ? 'var(--surface-raised)'
                              : 'transparent',
                            color: 'var(--text-primary)',
                          }}
                        >
                          {candidate.displayName}
                          <span
                            className="ml-1 font-normal"
                            style={{ color: 'var(--text-muted)' }}
                          >
                            {candidate.role}
                          </span>
                        </button>
                      )
                    })}
                  </div>
                </div>
                <div className="flex flex-wrap gap-2">
                  <input
                    type="text"
                    value={notes}
                    onChange={(event) => setNotes(event.target.value)}
                    placeholder="Notes (optional)"
                    aria-label="Notes"
                    className="min-w-0 flex-1 rounded border px-2 py-1 text-xs"
                    style={{
                      borderColor: 'var(--surface-border)',
                      background: 'var(--surface-raised)',
                      color: 'var(--text-primary)',
                    }}
                  />
                </div>
                <div className="flex flex-wrap gap-2">
                  {nextTransitions.map((next) => (
                    <button
                      key={next.status}
                      type="button"
                      disabled={!canAct || transition.isPending}
                      onClick={() => handleTransition(next.status)}
                      className="rounded border px-3 py-1 text-xs font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50"
                      style={{
                        borderColor: 'var(--surface-border)',
                        color: 'var(--text-primary)',
                      }}
                    >
                      {next.label}
                    </button>
                  ))}
                </div>
                {transition.isError && (
                  <p className="text-xs" style={{ color: 'var(--status-warning)' }}>
                    {transition.error instanceof Error
                      ? transition.error.message
                      : 'Failed to record investigation transition'}
                  </p>
                )}
              </div>
            ) : (
              <p className="mt-2 text-xs" style={{ color: 'var(--text-muted)' }}>
                This investigation is resolved.
              </p>
            )}
          </div>

          <div>
            <p
              className="text-lg font-semibold leading-snug"
              style={{ color: 'var(--text-primary)' }}
            >
              {recommendation.title}
            </p>
            <p
              className="mt-3 text-sm leading-relaxed"
              style={{ color: 'var(--text-secondary)' }}
            >
              {recommendation.description}
            </p>
          </div>

          <div
            className="rounded border px-4 py-4"
            style={{
              borderColor: 'var(--surface-border)',
              background: 'var(--surface-base)',
            }}
          >
            <p
              className="text-[10px] font-semibold uppercase tracking-wide"
              style={{ color: 'var(--text-muted)' }}
            >
              Steps
            </p>
            <ol
              className="mt-3 list-decimal space-y-3 pl-5 text-base leading-relaxed"
              style={{ color: 'var(--text-primary)' }}
            >
              {recommendation.recommended_steps.map((step, idx) => (
                <li key={`${recommendation.id}-${idx}`}>{step}</li>
              ))}
            </ol>
          </div>

          <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>
            <span className="font-medium" style={{ color: 'var(--text-muted)' }}>
              Estimated impact:
            </span>{' '}
            {recommendation.estimated_impact}
          </p>
        </div>
      ) : selectedAssetId ? (
        <p className="mt-4 text-sm" style={{ color: 'var(--text-muted)' }}>
          No recommendation available yet.
        </p>
      ) : (
        <p className="mt-4 text-sm" style={{ color: 'var(--text-muted)' }}>
          Select an asset to view the operator playbook.
        </p>
      )}
    </section>
  )
}
