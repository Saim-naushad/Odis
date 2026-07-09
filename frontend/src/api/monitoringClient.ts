import { apiClient } from './client'
import type {
  HealthResponse,
  MonitoringAssetHistoryItemResponse,
  MonitoringAssetLatestResponse,
  MonitoringAssetResponse,
  MonitoringRunDetailsResponse,
  PlatformMetadataResponse,
  TimelineEventResponse,
} from '../types/monitoring'

export const monitoringClient = {
  getHealth(signal?: AbortSignal): Promise<HealthResponse> {
    return apiClient.get('/health', signal)
  },

  getPlatformMetadata(signal?: AbortSignal): Promise<PlatformMetadataResponse> {
    return apiClient.get('/', signal)
  },

  listAssets(signal?: AbortSignal): Promise<MonitoringAssetResponse[]> {
    return apiClient.get('/monitoring/assets', signal)
  },

  getLatestForAsset(
    assetId: string,
    signal?: AbortSignal,
  ): Promise<MonitoringAssetLatestResponse> {
    return apiClient.get(
      `/monitoring/assets/${encodeURIComponent(assetId)}/latest`,
      signal,
    )
  },

  getHistoryForAsset(
    assetId: string,
    signal?: AbortSignal,
  ): Promise<MonitoringAssetHistoryItemResponse[]> {
    return apiClient.get(
      `/monitoring/assets/${encodeURIComponent(assetId)}/history`,
      signal,
    )
  },

  getRunDetails(
    runId: string,
    signal?: AbortSignal,
  ): Promise<MonitoringRunDetailsResponse> {
    return apiClient.get(
      `/monitoring/runs/${encodeURIComponent(runId)}`,
      signal,
    )
  },

  getTimelineForAsset(
    assetId: string,
    signal?: AbortSignal,
  ): Promise<TimelineEventResponse[]> {
    return apiClient.get(
      `/monitoring/assets/${encodeURIComponent(assetId)}/timeline`,
      signal,
    )
  },
}

