import { apiClient } from './client'
import type {
  HealthResponse,
  MonitoringAssetHistoryItemResponse,
  MonitoringAssetLatestResponse,
  MonitoringAssetResponse,
  MonitoringRunDetailsResponse,
  PlatformMetadataResponse,
} from '../types/monitoring'

export const monitoringClient = {
  getHealth(): Promise<HealthResponse> {
    return apiClient.get('/health')
  },

  getPlatformMetadata(): Promise<PlatformMetadataResponse> {
    return apiClient.get('/')
  },

  listAssets(): Promise<MonitoringAssetResponse[]> {
    return apiClient.get('/monitoring/assets')
  },

  getLatestForAsset(
    assetId: string,
  ): Promise<MonitoringAssetLatestResponse> {
    return apiClient.get(`/monitoring/assets/${encodeURIComponent(assetId)}/latest`)
  },

  getHistoryForAsset(
    assetId: string,
  ): Promise<MonitoringAssetHistoryItemResponse[]> {
    return apiClient.get(
      `/monitoring/assets/${encodeURIComponent(assetId)}/history`,
    )
  },

  getRunDetails(runId: string): Promise<MonitoringRunDetailsResponse> {
    return apiClient.get(
      `/monitoring/runs/${encodeURIComponent(runId)}`,
    )
  },
}

