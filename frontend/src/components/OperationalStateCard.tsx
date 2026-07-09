import type { OperationalStateResponse } from '../types/monitoring'

interface OperationalStateCardProps {
  selectedAssetId?: string
  operationalState?: OperationalStateResponse
  loading: boolean
  error?: string
}

export function OperationalStateCard({
  selectedAssetId,
  operationalState,
  loading,
  error,
}: OperationalStateCardProps) {
  return (
    <section className="rounded border border-slate-800 bg-slate-900/40 p-4">
      <div className="flex items-center justify-between gap-2">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-300">
          Operational state
        </h2>
        {loading && !error && (
          <span className="text-[10px] uppercase tracking-wide text-slate-500">
            Refreshing…
          </span>
        )}
      </div>
      {error ? (
        <p className="mt-2 text-xs text-amber-400">{error}</p>
      ) : operationalState ? (
        <div className="mt-3 grid gap-4 text-xs md:grid-cols-3">
          <div className="rounded border border-slate-800 bg-slate-950/60 p-3">
            <p className="text-[10px] font-semibold uppercase tracking-wide text-slate-400">
              Health
            </p>
            <p className="mt-1 text-lg font-semibold text-slate-50">
              {operationalState.health_score}/100
            </p>
            <p className="mt-1 text-[11px] text-slate-300">
              Status: {operationalState.health_status}
            </p>
          </div>
          <div className="rounded border border-slate-800 bg-slate-950/60 p-3">
            <p className="text-[10px] font-semibold uppercase tracking-wide text-slate-400">
              Risk & confidence
            </p>
            <p className="mt-1 text-[11px] text-slate-100">
              Risk: {operationalState.risk_level}
            </p>
            <p className="mt-1 text-[11px] text-slate-100">
              Confidence: {operationalState.confidence}/100
            </p>
            <p className="mt-1 text-[10px] text-slate-500">
              Updated: {new Date(operationalState.last_updated).toLocaleString()}
            </p>
          </div>
          <div className="rounded border border-slate-800 bg-slate-950/60 p-3">
            <p className="text-[10px] font-semibold uppercase tracking-wide text-slate-400">
              Driver & action
            </p>
            <p className="mt-1 text-[11px] text-slate-200">
              <span className="text-slate-500">Primary driver:</span>{' '}
              {operationalState.primary_driver}
            </p>
            <p className="mt-2 text-[11px] text-slate-200">
              <span className="text-slate-500">Recommended action:</span>{' '}
              {operationalState.recommended_action}
            </p>
          </div>
        </div>
      ) : selectedAssetId ? (
        <p className="mt-2 text-xs text-slate-500">
          No operational state available yet.
        </p>
      ) : (
        <p className="mt-2 text-xs text-slate-500">
          Select an asset to view its operational state.
        </p>
      )}
    </section>
  )
}

