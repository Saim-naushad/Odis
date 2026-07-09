import { apiClient } from './client'
import type {
  HealthResponse,
  MonitoringAssetHistoryItemResponse,
  MonitoringAssetLatestResponse,
  MonitoringAssetResponse,
  MonitoringRunDetailsResponse,
  OperationalStateResponse,
  PlatformMetadataResponse,
  NotificationResponse,
  RecommendationResponse,
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

  getOperationalStateForAsset(
    assetId: string,
    signal?: AbortSignal,
  ): Promise<OperationalStateResponse> {
    return apiClient.get(
      `/monitoring/assets/${encodeURIComponent(assetId)}/state`,
      signal,
    )
  },

  getRecommendationForAsset(
    assetId: string,
    signal?: AbortSignal,
  ): Promise<RecommendationResponse> {
    return apiClient.get(
      `/monitoring/assets/${encodeURIComponent(assetId)}/recommendation`,
      signal,
    )
  },

  getNotificationForAsset(
    assetId: string,
    signal?: AbortSignal,
  ): Promise<NotificationResponse | null> {
    const path = `/monitoring/assets/${encodeURIComponent(assetId)}/notification`
    return apiClient.get<NotificationResponse>(path, signal).catch((error) => {
      if (error instanceof Error && error.message.includes('failed with 404')) {
        return null
      }
      throw error
    })
  },
}

