import type { MonitoringAssetResponse } from '../types/monitoring'

/**
 * Fleet strip ordering for PR140.
 *
 * Future: replace with `GET /monitoring/fleet-summary` returning per-asset
 * `{ id, asset_name, health_score, health_status, recommendation_priority,
 * has_open_notification }` to enable true cross-fleet attention ranking
 * without N+1 digital-twin fetches.
 */
export function sortAssetsForFleetStrip(
  assets: MonitoringAssetResponse[],
  selectedAssetId?: string,
): MonitoringAssetResponse[] {
  const sorted = [...assets].sort((a, b) => a.id.localeCompare(b.id))

  if (!selectedAssetId) {
    return sorted
  }

  const selectedIndex = sorted.findIndex((asset) => asset.id === selectedAssetId)
  if (selectedIndex <= 0) {
    return sorted
  }

  const selected = sorted[selectedIndex]
  const rest = sorted.filter((asset) => asset.id !== selectedAssetId)
  return [selected, ...rest]
}
