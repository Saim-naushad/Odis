import type { MonitoringAssetResponse } from '../types/monitoring'

/**
 * Fleet strip ordering: alphabetical by id, with the selected asset pinned
 * first. `MonitoringAssetResponse` already carries a per-asset health
 * snapshot (see PR151), so this only controls chip order, not what each
 * chip displays.
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
