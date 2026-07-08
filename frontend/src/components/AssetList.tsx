import type {
  MonitoringAssetHistoryItemResponse,
  MonitoringAssetLatestResponse,
  MonitoringAssetResponse,
} from '../types/monitoring'

interface AssetListProps {
  assets: MonitoringAssetResponse[]
  selectedAssetId?: string
  onSelectAsset: (assetId: string) => void
  selectedRunId?: string
  latest?: MonitoringAssetLatestResponse
  history: MonitoringAssetHistoryItemResponse[]
  loading: boolean
  error?: string
  onRetry?: () => void | Promise<void>
}

export function AssetList({
  assets,
  selectedAssetId,
  onSelectAsset,
  selectedRunId,
  latest,
  history,
  loading,
  error,
  onRetry,
}: AssetListProps) {
  return (
    <section className="flex h-full flex-col gap-3">
      <div className="flex items-center justify-between">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-300">
          Assets
        </h2>
        {loading && (
          <span className="text-[10px] uppercase tracking-wide text-slate-500">
            Refreshing…
          </span>
        )}
      </div>
      {error && (
        <div className="flex items-start justify-between gap-2">
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
      <div className="grid gap-3">
        {assets.map((asset) => {
          const isSelected = asset.id === selectedAssetId
          const latestForAsset =
            latest && latest.asset_id === asset.id ? latest : undefined
          const selectedRunForAsset =
            isSelected && selectedRunId
              ? history.find(
                  (item) => item.asset_id === asset.id && item.run_id === selectedRunId,
                )
              : undefined

          const selectedRunLatestForAsset =
            isSelected && selectedRunId && latestForAsset?.run_id === selectedRunId
              ? latestForAsset
              : undefined

          const lastEntry =
            selectedRunForAsset ??
            selectedRunLatestForAsset ??
            history.find((item) => item.asset_id === asset.id) ??
            latestForAsset

          return (
            <button
              key={asset.id}
              type="button"
              onClick={() => onSelectAsset(asset.id)}
              className={`flex flex-col items-start rounded border px-3 py-2 text-left text-xs transition-colors ${
                isSelected
                  ? 'border-emerald-500/80 bg-slate-900'
                  : 'border-slate-800 bg-slate-900/40 hover:border-slate-600'
              }`}
            >
              <div className="flex w-full items-center justify-between gap-2">
                <span className="font-mono text-[11px] text-slate-100">
                  {asset.id}
                </span>
                {lastEntry && (
                  <span className="rounded bg-slate-800 px-1.5 py-0.5 text-[10px] text-slate-300">
                    {lastEntry.decision_plan.priority.toUpperCase()}
                  </span>
                )}
              </div>
              {lastEntry && (
                <p className="mt-1 line-clamp-2 text-[11px] text-slate-300">
                  {lastEntry.decision_plan.recommendation}
                </p>
              )}
              {lastEntry && (
                <p className="mt-1 text-[10px] text-slate-500">
                  Last run:{' '}
                  {new Date(lastEntry.timestamp).toLocaleTimeString()}
                </p>
              )}
            </button>
          )
        })}
        {assets.length === 0 && !loading && (
          <p className="text-xs text-slate-500">
            No assets reported yet.
          </p>
        )}
      </div>
    </section>
  )
}

