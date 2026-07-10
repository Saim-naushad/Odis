import type { DigitalTwinResponse, MonitoringAssetResponse } from '../../types/monitoring'
import { sortAssetsForFleetStrip } from '../../utils/fleetAttention'
import {
  healthStatusBadgeClass,
  healthStatusDotClass,
} from '../../utils/healthStatus'

interface FleetAttentionStripProps {
  assets: MonitoringAssetResponse[]
  selectedAssetId?: string
  selectedDigitalTwin?: DigitalTwinResponse
  loading: boolean
  error?: string
  onSelectAsset: (assetId: string) => void
  onRetry?: () => void | Promise<void>
}

export function FleetAttentionStrip({
  assets,
  selectedAssetId,
  selectedDigitalTwin,
  loading,
  error,
  onSelectAsset,
  onRetry,
}: FleetAttentionStripProps) {
  const orderedAssets = sortAssetsForFleetStrip(assets, selectedAssetId)

  return (
    <section
      className="border-b px-4 py-2"
      style={{
        borderColor: 'var(--surface-border)',
        background: 'var(--surface-base)',
      }}
      aria-label="Fleet attention"
    >
      <div className="mb-1.5 flex items-center justify-between gap-2">
        <h2
          className="text-[10px] font-semibold uppercase tracking-wide"
          style={{ color: 'var(--text-secondary)' }}
        >
          Assets
        </h2>
        {loading && (
          <span
            className="text-[10px] uppercase tracking-wide"
            style={{ color: 'var(--text-muted)' }}
          >
            Refreshing…
          </span>
        )}
      </div>

      {error && (
        <div className="mb-2 flex items-start justify-between gap-2">
          <p className="text-xs" style={{ color: 'var(--status-warning)' }}>
            {error}
          </p>
          {onRetry && (
            <button
              type="button"
              className="rounded border px-2 py-0.5 text-[10px] transition-colors hover:opacity-80 disabled:cursor-not-allowed disabled:opacity-50"
              style={{
                borderColor: 'var(--surface-border)',
                color: 'var(--text-secondary)',
              }}
              onClick={() => void onRetry()}
              disabled={loading}
            >
              Retry
            </button>
          )}
        </div>
      )}

      <div className="flex gap-2 overflow-x-auto pb-1">
        {orderedAssets.map((asset) => {
          const isSelected = asset.id === selectedAssetId
          const isSelectedWithTwin =
            isSelected && selectedDigitalTwin?.asset_id === asset.id

          const label = isSelectedWithTwin
            ? selectedDigitalTwin.asset_name || asset.id
            : asset.id

          const healthStatus = isSelectedWithTwin
            ? selectedDigitalTwin.operational_state.health_status
            : undefined

          const healthScore = isSelectedWithTwin
            ? selectedDigitalTwin.operational_state.health_score
            : undefined

          const hasNotification = isSelectedWithTwin && Boolean(selectedDigitalTwin.notification)

          return (
            <button
              key={asset.id}
              type="button"
              onClick={() => onSelectAsset(asset.id)}
              className={`flex shrink-0 items-center gap-2 rounded border px-3 py-2 text-left text-xs transition-colors ${
                isSelected ? 'focus-ring-active' : 'hover:opacity-90'
              }`}
              style={{
                borderColor: isSelected ? 'var(--focus-ring)' : 'var(--surface-border)',
                background: isSelected ? 'var(--surface-raised)' : 'transparent',
                color: 'var(--text-primary)',
              }}
              aria-pressed={isSelected}
            >
              {hasNotification && (
                <span
                  className={`inline-flex h-2 w-2 shrink-0 rounded-full ${healthStatusDotClass(healthStatus ?? 'WARNING')}`}
                  aria-label="Active notification"
                />
              )}

              <span className="max-w-[10rem] truncate font-medium">{label}</span>

              {isSelectedWithTwin && healthStatus && (
                <span className={`status-badge ${healthStatusBadgeClass(healthStatus)}`}>
                  {healthStatus}
                </span>
              )}

              {isSelectedWithTwin && healthScore !== undefined && (
                <span className="text-[10px]" style={{ color: 'var(--text-muted)' }}>
                  {healthScore}
                </span>
              )}
            </button>
          )
        })}

        {assets.length === 0 && !loading && (
          <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
            No assets connected.
          </p>
        )}
      </div>
    </section>
  )
}
