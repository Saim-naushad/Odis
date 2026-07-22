export type MonitoringEventType =
  | 'asset_updated'
  | 'run_updated'
  | 'platform_updated'
  | 'fault_investigation_updated'

export interface MonitoringSsePayload {
  type: MonitoringEventType | string
  asset_id?: string
  run_id?: string
  timestamp?: string
}
