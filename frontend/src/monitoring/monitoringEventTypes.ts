export type MonitoringEventType =
  | 'asset_updated'
  | 'run_updated'
  | 'platform_updated'

export interface MonitoringSsePayload {
  type: MonitoringEventType | string
  asset_id?: string
  run_id?: string
  timestamp?: string
}
