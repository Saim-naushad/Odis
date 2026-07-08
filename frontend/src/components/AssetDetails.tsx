import type {
  MonitoringAssetLatestResponse,
  MonitoringRunDetailsResponse,
} from '../types/monitoring'

interface AssetDetailsProps {
  latest?: MonitoringAssetLatestResponse
  runDetails?: MonitoringRunDetailsResponse
  loading: boolean
  error?: string
}

export function AssetDetails({
  latest,
  runDetails,
  loading,
  error,
}: AssetDetailsProps) {
  if (!latest && !loading && !error) {
    return (
      <section className="flex h-full flex-col rounded border border-slate-800 bg-slate-900/40 p-4">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-300">
          Selected asset
        </h2>
        <p className="mt-2 text-xs text-slate-500">
          Select an asset to inspect its latest reasoning run.
        </p>
      </section>
    )
  }

  return (
    <section className="flex h-full flex-col rounded border border-slate-800 bg-slate-900/40 p-4">
      <div className="flex items-center justify-between gap-2">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-300">
          Selected asset
        </h2>
        {loading && (
          <span className="text-[10px] uppercase tracking-wide text-slate-500">
            Refreshing…
          </span>
        )}
      </div>
      {error && (
        <p className="mt-2 text-xs text-amber-400">{error}</p>
      )}
      {latest && (
        <div className="mt-3 space-y-3 text-xs">
          <div className="flex flex-wrap items-center gap-3">
            <span className="font-mono text-[11px] text-slate-100">
              {latest.asset_id}
            </span>
            <span className="rounded bg-slate-800 px-2 py-0.5 text-[10px]">
              Run {latest.run_id}
            </span>
            <span className="text-[10px] text-slate-400">
              {new Date(latest.timestamp).toLocaleString()}
            </span>
          </div>

          <div>
            <h3 className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">
              Current measurements
            </h3>
            {runDetails ? (
              <div className="mt-1 max-h-40 space-y-1 overflow-y-auto rounded border border-slate-800 bg-slate-950/60 p-2">
                {runDetails.observations.map((obs) => (
                  <div
                    key={obs.id}
                    className="flex items-center justify-between gap-2"
                  >
                    <span className="font-mono text-[10px] text-slate-400">
                      {obs.measurement_type}
                    </span>
                    <span className="font-mono text-[10px] text-slate-100">
                      {obs.value} {obs.unit}
                    </span>
                    <span className="text-[10px] text-slate-500">
                      {new Date(obs.timestamp).toLocaleTimeString()}
                    </span>
                  </div>
                ))}
                {runDetails.observations.length === 0 && (
                  <p className="text-[11px] text-slate-500">
                    No observations recorded for this run.
                  </p>
                )}
              </div>
            ) : (
              <p className="mt-1 text-[11px] text-slate-500">
                No observation data available.
              </p>
            )}
          </div>

          <div className="grid gap-3 md:grid-cols-2">
            <div>
              <h3 className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">
                Structured assessment
              </h3>
              {runDetails?.structured_assessment ? (
                <dl className="mt-1 grid grid-cols-2 gap-x-3 gap-y-1 text-[11px]">
                  <dt className="text-slate-500">Trend</dt>
                  <dd className="text-slate-100">
                    {runDetails.structured_assessment.trend_direction}
                  </dd>
                  <dt className="text-slate-500">Variation</dt>
                  <dd className="text-slate-100">
                    {runDetails.structured_assessment.variation_level}
                  </dd>
                  <dt className="text-slate-500">Correlations</dt>
                  <dd className="text-slate-100">
                    {runDetails.structured_assessment.has_correlations
                      ? 'Present'
                      : 'None'}
                  </dd>
                  <dt className="text-slate-500">Contradictions</dt>
                  <dd className="text-slate-100">
                    {runDetails.structured_assessment.has_contradictions
                      ? 'Present'
                      : 'None'}
                  </dd>
                  <dt className="text-slate-500">Unexpected expectations</dt>
                  <dd className="text-slate-100">
                    {runDetails.structured_assessment
                      .has_unexpected_expectations
                      ? 'Present'
                      : 'None'}
                  </dd>
                  <dt className="text-slate-500">Indeterminate expectations</dt>
                  <dd className="text-slate-100">
                    {runDetails.structured_assessment
                      .has_indeterminate_expectations
                      ? 'Present'
                      : 'None'}
                  </dd>
                </dl>
              ) : (
                <p className="mt-1 text-[11px] text-slate-500">
                  No structured assessment available for this run.
                </p>
              )}
            </div>

            <div>
              <h3 className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">
                Decision summary
              </h3>
              {runDetails ? (
                <div className="mt-1 space-y-1 text-[11px]">
                  <p className="text-slate-100">
                    {runDetails.decision_plan.recommendation}
                  </p>
                  <p className="text-slate-400">
                    Priority: {runDetails.decision_plan.priority}
                  </p>
                  <p className="text-slate-400">
                    Justification: {runDetails.decision_plan.justification}
                  </p>
                </div>
              ) : (
                <p className="mt-1 text-[11px] text-slate-500">
                  No decision plan details available.
                </p>
              )}
            </div>
          </div>
        </div>
      )}
    </section>
  )
}

