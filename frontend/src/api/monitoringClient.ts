import { apiClient } from './client'
import type {
  HealthResponse,
  DigitalTwinResponse,
  InvestigationTransitionRequest,
  InvestigationTransitionResponse,
  MonitoringAssetHistoryItemResponse,
  MonitoringAssetLatestResponse,
  MonitoringAssetResponse,
  MonitoringRunDetailsResponse,
  OperationalStateResponse,
  PlatformMetadataResponse,
  NotificationResponse,
  RecommendationResponse,
  TelemetrySeriesResponse,
  TelemetryAggregateSeriesResponse,
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

  getDigitalTwinForAsset(
    assetId: string,
    signal?: AbortSignal,
  ): Promise<DigitalTwinResponse> {
    return apiClient.get(
      `/monitoring/assets/${encodeURIComponent(assetId)}/digital-twin`,
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

  getTelemetryHistoryForAsset(
    assetId: string,
    signal?: AbortSignal,
    params?: {
      start?: string
      end?: string
      measurement_type?: string
      limit?: number
    },
  ): Promise<TelemetrySeriesResponse[]> {
    const search = new URLSearchParams()
    if (params?.start) search.set('start', params.start)
    if (params?.end) search.set('end', params.end)
    if (params?.measurement_type) {
      search.set('measurement_type', params.measurement_type)
    }
    if (params?.limit !== undefined) {
      search.set('limit', String(params.limit))
    }
    const query = search.toString()
    const path = `/monitoring/assets/${encodeURIComponent(assetId)}/telemetry${
      query ? `?${query}` : ''
    }`
    return apiClient.get(path, signal)
  },

  getLatestTelemetryForAsset(
    assetId: string,
    signal?: AbortSignal,
    params?: {
      measurement_type?: string
      limit?: number
    },
  ): Promise<TelemetrySeriesResponse[]> {
    const search = new URLSearchParams()
    if (params?.measurement_type) {
      search.set('measurement_type', params.measurement_type)
    }
    if (params?.limit !== undefined) {
      search.set('limit', String(params.limit))
    }
    const query = search.toString()
    const path = `/monitoring/assets/${encodeURIComponent(assetId)}/telemetry/latest${
      query ? `?${query}` : ''
    }`
    return apiClient.get(path, signal)
  },

  recordInvestigationTransition(
    assetId: string,
    payload: InvestigationTransitionRequest,
  ): Promise<InvestigationTransitionResponse> {
    return apiClient.post(
      `/monitoring/assets/${encodeURIComponent(assetId)}/investigation`,
      payload,
    )
  },

  getTelemetryAggregatesForAsset(
    assetId: string,
    signal?: AbortSignal,
    params?: {
      bucket: '1h' | '1d'
      start?: string
      end?: string
      measurement_type?: string
    },
  ): Promise<TelemetryAggregateSeriesResponse[]> {
    const search = new URLSearchParams()
    search.set('bucket', params?.bucket ?? '1h')
    if (params?.start) search.set('start', params.start)
    if (params?.end) search.set('end', params.end)
    if (params?.measurement_type) {
      search.set('measurement_type', params.measurement_type)
    }
    const query = search.toString()
    const path = `/monitoring/assets/${encodeURIComponent(assetId)}/telemetry/aggregate?${query}`
    return apiClient.get(path, signal)
  },
}

