import type { FaultInvestigationSummaryResponse } from '../../types/monitoring'
import {
  corroborationResultVariant,
  faultUrgencyVariant,
  semanticBadgeClass,
} from '../../utils/statusBadges'

interface ActiveFaultInvestigationCardProps {
  selectedAssetId?: string
  investigation: FaultInvestigationSummaryResponse | null | undefined
  loading: boolean
  error?: string
  onOpenHistory: () => void
  historyDisabled: boolean
}

function readableLabel(value: string): string {
  return value.replace(/_/g, ' ')
}

// Fault state -> corroboration -> urgency -> recommendation -> authority
// boundary -> supporting evidence -> provenance (collapsed). Never leads
// with model internals — the diagnostic score only appears in the
// collapsed provenance section, always paired with its caveat sentence.
export function ActiveFaultInvestigationCard({
  selectedAssetId,
  investigation,
  loading,
  error,
  onOpenHistory,
  historyDisabled,
}: ActiveFaultInvestigationCardProps) {
  return (
    <section
      className="rounded border px-6 py-6"
      style={{
        borderColor: investigation
          ? 'var(--status-warning)'
          : 'var(--surface-border)',
        borderLeftWidth: investigation ? '4px' : undefined,
        background: 'var(--surface-raised)',
      }}
      aria-label="AI-assisted fault diagnosis"
    >
      <div className="flex items-center justify-between gap-2">
        <div>
          <h2
            className="text-xs font-semibold uppercase tracking-wide"
            style={{ color: 'var(--text-secondary)' }}
          >
            AI-Assisted Fault Diagnosis
          </h2>
          <p className="mt-1 text-[10px]" style={{ color: 'var(--text-muted)' }}>
            Diagnostic model alert, evaluated by deterministic telemetry rules
          </p>
        </div>
        <button
          type="button"
          onClick={onOpenHistory}
          disabled={historyDisabled}
          className="rounded border px-2 py-1 text-[11px] font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50"
          style={{ borderColor: 'var(--surface-border)', color: 'var(--text-secondary)' }}
        >
          Investigation history
        </button>
      </div>

      {/* A refresh error never hides last-good content: the banner and the
          content below are independent, so a transient background-refetch
          failure surfaces without discarding a still-valid diagnosis. */}
      {error && (
        <p className="mt-4 text-sm" role="alert" style={{ color: 'var(--status-warning)' }}>
          {error}
        </p>
      )}
      {loading ? (
        <p className="mt-4 text-sm" style={{ color: 'var(--text-muted)' }}>
          Loading AI fault investigation…
        </p>
      ) : !selectedAssetId ? (
        <p className="mt-4 text-sm" style={{ color: 'var(--text-muted)' }}>
          Select an asset to view AI-assisted fault diagnosis.
        </p>
      ) : investigation ? (
        <div className="mt-5 space-y-5">
          {/* Fault state */}
          <div className="flex flex-wrap items-center gap-2">
            <span className="status-badge status-badge-info">
              {readableLabel(investigation.diagnosed_fault_class)}
            </span>
            <span className="status-badge status-badge-normal">
              {readableLabel(investigation.alert_transition_type)}
            </span>
            {investigation.previous_diagnosed_fault_class && (
              <span
                className="text-[10px]"
                style={{ color: 'var(--text-muted)' }}
              >
                (was {readableLabel(investigation.previous_diagnosed_fault_class)})
              </span>
            )}
            <span className="text-[10px]" style={{ color: 'var(--text-muted)' }}>
              {new Date(investigation.observed_at).toLocaleString()}
            </span>
          </div>

          {/* Corroboration */}
          <div
            className="rounded border px-4 py-4"
            style={{ borderColor: 'var(--surface-border)', background: 'var(--surface-base)' }}
          >
            <div className="flex flex-wrap items-center gap-2">
              <p
                className="text-[10px] font-semibold uppercase tracking-wide"
                style={{ color: 'var(--text-muted)' }}
              >
                Deterministic corroboration
              </p>
              <span
                className={`status-badge ${semanticBadgeClass(
                  corroborationResultVariant(investigation.corroboration_result),
                )}`}
              >
                {readableLabel(investigation.corroboration_result)}
              </span>
              {investigation.urgency && (
                <span
                  className={`status-badge ${semanticBadgeClass(
                    faultUrgencyVariant(investigation.urgency),
                  )}`}
                >
                  {readableLabel(investigation.urgency)}
                </span>
              )}
            </div>
            <p className="mt-2 text-xs leading-relaxed" style={{ color: 'var(--text-secondary)' }}>
              {investigation.corroboration_notes}
            </p>
            {investigation.corroboration_rule_ids.length > 0 && (
              <div className="mt-2 flex flex-wrap gap-1">
                {investigation.corroboration_rule_ids.map((ruleId) => (
                  <span
                    key={ruleId}
                    className="rounded border px-2 py-0.5 text-[10px]"
                    style={{ borderColor: 'var(--surface-border)', color: 'var(--text-muted)' }}
                  >
                    {ruleId}
                  </span>
                ))}
              </div>
            )}
          </div>

          {/* Recommendation */}
          <div
            className="rounded border px-4 py-4"
            style={{ borderColor: 'var(--surface-border)', background: 'var(--surface-base)' }}
          >
            <p
              className="text-[10px] font-semibold uppercase tracking-wide"
              style={{ color: 'var(--text-muted)' }}
            >
              {investigation.recommendation?.status === 'withheld'
                ? 'Recommendation withheld'
                : 'Recommended next step'}
            </p>
            {investigation.recommendation ? (
              <div className="mt-2 space-y-2">
                <p className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
                  {investigation.recommendation.action_summary}
                </p>
                <p className="text-xs leading-relaxed" style={{ color: 'var(--text-secondary)' }}>
                  {investigation.recommendation.reason}
                </p>
                {investigation.recommendation.recommended_steps.length > 0 && (
                  <ol
                    className="list-decimal space-y-1 pl-5 text-xs leading-relaxed"
                    style={{ color: 'var(--text-primary)' }}
                  >
                    {investigation.recommendation.recommended_steps.map((step, idx) => (
                      <li key={`${investigation.recommendation!.id}-${idx}`}>{step}</li>
                    ))}
                  </ol>
                )}
                <p className="text-[11px] italic" style={{ color: 'var(--text-muted)' }}>
                  {investigation.recommendation.limitations}
                </p>
              </div>
            ) : (
              <p className="mt-2 text-xs" style={{ color: 'var(--text-muted)' }}>
                This fault has been cleared; no active recommendation.
              </p>
            )}
          </div>

          {/* Authority boundary — always visible, never collapsed */}
          <p
            className="text-[11px] leading-relaxed"
            style={{ color: 'var(--text-muted)' }}
          >
            {investigation.authority_boundary_note}
          </p>

          {/* Supporting evidence */}
          {investigation.supporting_evidence.length > 0 && (
            <div>
              <p
                className="text-[10px] font-semibold uppercase tracking-wide"
                style={{ color: 'var(--text-muted)' }}
              >
                Supporting observations
              </p>
              <div className="mt-2 overflow-x-auto">
                <table className="w-full text-left text-xs" style={{ color: 'var(--text-secondary)' }}>
                  <thead>
                    <tr style={{ color: 'var(--text-muted)' }}>
                      <th className="pb-1 pr-4 font-medium">Measurement</th>
                      <th className="pb-1 pr-4 font-medium">Value</th>
                      <th className="pb-1 font-medium">Observed</th>
                    </tr>
                  </thead>
                  <tbody>
                    {investigation.supporting_evidence.map((observation) => (
                      <tr key={observation.observation_id}>
                        <td className="py-0.5 pr-4">{observation.measurement_type}</td>
                        <td className="py-0.5 pr-4">
                          {observation.value} {observation.unit}
                        </td>
                        <td className="py-0.5">
                          {new Date(observation.observed_at).toLocaleTimeString()}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Provenance — collapsed, secondary tier */}
          {investigation.provenance && (
            <details className="rounded border px-4 py-3" style={{ borderColor: 'var(--surface-border)' }}>
              <summary
                className="cursor-pointer text-[10px] font-semibold uppercase tracking-wide"
                style={{ color: 'var(--text-muted)' }}
              >
                Model &amp; provenance details
              </summary>
              <div className="mt-3 space-y-1 text-[11px]" style={{ color: 'var(--text-secondary)' }}>
                <p>
                  Diagnostic model score: {investigation.provenance.latest_model_score.toFixed(2)}
                </p>
                <p style={{ color: 'var(--text-muted)' }}>
                  {investigation.provenance.score_semantics}
                </p>
                <p>Model version: {investigation.provenance.model_system_version}</p>
                <p>Model hash: {investigation.provenance.model_hash}</p>
                <p>Policy hash: {investigation.provenance.policy_hash}</p>
                <p>Feature schema: {investigation.provenance.feature_schema_version}</p>
                <p>Source event: {investigation.provenance.source_event_id}</p>
                <p>Recorded: {new Date(investigation.provenance.recorded_at).toLocaleString()}</p>
              </div>
            </details>
          )}
        </div>
      ) : (
        !error && (
          <p className="mt-4 text-sm" role="status" style={{ color: 'var(--text-muted)' }}>
            No active AI-detected fault investigation for this asset.
          </p>
        )
      )}
    </section>
  )
}
