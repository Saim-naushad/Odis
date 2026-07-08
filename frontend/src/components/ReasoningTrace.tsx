import type { ReasoningTraceResponse } from '../types/monitoring'

interface ReasoningTraceProps {
  trace?: ReasoningTraceResponse | null
  loading: boolean
  error?: string
  onRetry?: () => void | Promise<void>
}

export function ReasoningTrace({
  trace,
  loading,
  error,
  onRetry,
}: ReasoningTraceProps) {
  return (
    <section className="flex h-full flex-col rounded border border-slate-800 bg-slate-900/40 p-4">
      <div className="flex items-center justify-between gap-2">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-300">
          Reasoning trace
        </h2>
        {loading && !error && (
          <span className="text-[10px] uppercase tracking-wide text-slate-500">
            Refreshing…
          </span>
        )}
      </div>
      {error && (
        <div className="mt-2 flex items-start justify-between gap-2">
          <p className="text-xs text-amber-400">{error}</p>
          {onRetry && (
            <button
              type="button"
              className="rounded border border-slate-700 px-2 py-0.5 text-[10px] text-slate-300 transition-colors hover:border-slate-500 disabled:cursor-not-allowed disabled:opacity-50"
              onClick={() => void onRetry()}
              disabled={loading}
            >
              Retry
            </button>
          )}
        </div>
      )}
      <div className="mt-3 flex-1 overflow-y-auto rounded border border-slate-800 bg-slate-950/60 p-3">
        {trace && trace.steps.length > 0 ? (
          <ol className="space-y-2 text-xs">
            {trace.steps.map((step, index) => (
              <li key={`${step.name}-${index}`} className="flex gap-3">
                <span className="mt-0.5 h-5 w-5 flex-shrink-0 rounded-full border border-slate-700 bg-slate-900 text-center text-[10px] leading-5 text-slate-300">
                  {index + 1}
                </span>
                <div>
                  <p className="font-mono text-[11px] text-emerald-300">
                    {step.name}
                  </p>
                  <p className="mt-0.5 text-[11px] text-slate-200">
                    {step.description}
                  </p>
                </div>
              </li>
            ))}
          </ol>
        ) : !error && loading ? (
          <div className="flex h-full items-center justify-center px-3">
            <p className="text-xs text-slate-500">Loading trace…</p>
          </div>
        ) : (
          !error && (
            <p className="text-xs text-slate-500">
              No reasoning trace available for this run.
            </p>
          )
        )}
      </div>
    </section>
  )
}

