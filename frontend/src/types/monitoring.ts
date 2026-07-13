export interface HealthResponse {
  status: string
}

export interface PlatformMetadataResponse {
  platform_name: string
  reasoning_engine_version: string
  platform_phase: string
}

export interface MonitoringAssetResponse {
  id: string
}

export interface OperationalSituationResponse {
  id: string
  goal_id: string
  observation_ids: string[]
  assessment: string
}

export interface StructuredAssessmentResponse {
  trend_direction: string
  variation_level: string
  has_correlations: boolean
  has_contradictions: boolean
  has_unexpected_expectations: boolean
  has_indeterminate_expectations: boolean
}

export interface DecisionPlanSummaryResponse {
  id: string
  priority: string
  recommendation: string
}

export interface EvidenceResponse {
  id: string
  description: string
  measurement_type: string
  observed_value: string
  contribution_weight: number
}

export interface ConfidenceScoreResponse {
  value: number
  rationale: string
}

export interface AlternativeHypothesisResponse {
  title: string
  reason: string
  confidence: number
}

export interface DecisionPlanResponse extends DecisionPlanSummaryResponse {
  context_id: string
  created_at: string
  justification: string
  confidence?: ConfidenceScoreResponse | null
  evidence?: EvidenceResponse[]
  alternative_hypotheses?: AlternativeHypothesisResponse[]
  expected_outcome?: string | null
}

export interface DecisionContextResponse {
  id: string
  goal_id: string
  situation_id: string
  assessment: string
  created_at: string
}

export interface ObservationResponse {
  id: string
  asset_id: string
  timestamp: string
  measurement_type: string
  value: number
  unit: string
}

export interface TelemetrySampleResponse {
  timestamp: string
  value: number
}

export interface TelemetrySeriesResponse {
  asset_id: string
  measurement_type: string
  unit: string
  samples: TelemetrySampleResponse[]
}

export interface TelemetryAggregateSampleResponse {
  timestamp: string
  avg_value: number
  min_value: number
  max_value: number
  sample_count: number
}

export interface TelemetryAggregateSeriesResponse {
  asset_id: string
  measurement_type: string
  unit: string
  bucket: '1h' | '1d' | string
  samples: TelemetryAggregateSampleResponse[]
}

export interface TraceStepResponse {
  name: string
  description: string
}

export interface ReasoningTraceResponse {
  steps: TraceStepResponse[]
}

export interface MonitoringAssetLatestResponse {
  asset_id: string
  run_id: string
  timestamp: string
  operational_situation: OperationalSituationResponse
  structured_assessment: StructuredAssessmentResponse | null
  decision_plan: DecisionPlanSummaryResponse
}

export interface MonitoringAssetHistoryItemResponse {
  asset_id: string
  run_id: string
  timestamp: string
  operational_situation: OperationalSituationResponse
  structured_assessment: StructuredAssessmentResponse | null
  decision_plan: DecisionPlanSummaryResponse
}

export interface MonitoringRunDetailsResponse {
  run_id: string
  started_at: string
  observations: ObservationResponse[]
  reasoning_trace: ReasoningTraceResponse | null
  structured_assessment: StructuredAssessmentResponse | null
  operational_situation: OperationalSituationResponse
  decision_context: DecisionContextResponse
  decision_plan: DecisionPlanResponse
  trend_analysis?: TrendAnalysisResponse | null
}

export interface TrendAnalysisResponse {
  direction: 'rising' | 'falling' | 'stable' | string
  rate_of_change: number
  stability_score: number
  volatility_score: number
  summary: string
}

export interface OperationalStateResponse {
  asset_id: string
  health_score: number
  health_status: 'NORMAL' | 'WARNING' | 'CRITICAL' | string
  risk_level: 'LOW' | 'MEDIUM' | 'HIGH' | string
  confidence: number
  primary_driver: string
  recommended_action: string
  last_updated: string
}

export interface RecommendationResponse {
  id: string
  asset_id: string
  category: 'investigate' | 'mitigate' | 'monitor' | string
  priority: 'P0' | 'P1' | 'P2' | 'P3' | string
  urgency: 'IMMEDIATE' | 'SOON' | 'SCHEDULED' | string
  title: string
  description: string
  recommended_steps: string[]
  estimated_impact: string
  created_at: string
}

export interface NotificationResponse {
  id: string
  asset_id: string
  recommendation_id: string
  severity: 'INFO' | 'WARNING' | 'CRITICAL' | string
  status: 'OPEN' | 'ACKNOWLEDGED' | 'RESOLVED' | string
  title: string
  message: string
  created_at: string
}

export interface LocationResponse {
  identifier: string
}

export type InvestigationStatus = 'ACKNOWLEDGED' | 'INVESTIGATING' | 'RESOLVED'

export interface InvestigationTransitionResponse {
  id: string
  asset_id: string
  recommendation_id: string
  status: InvestigationStatus | string
  actor_id: string
  actor_display_name: string
  occurred_at: string
  notes: string | null
}

export interface InvestigationTransitionRequest {
  recommendation_id: string
  status: InvestigationStatus
  actor_id: string
  actor_display_name: string
  notes?: string | null
}

export type TimelineEventType =
  | 'observation_received'
  | 'reasoning_started'
  | 'reasoning_completed'
  | 'recommendation_updated'
  | 'notification_created'
  | 'trend_changed'
  | 'health_changed'
  | 'risk_changed'
  | 'investigation_transition'

export interface TimelineEventResponse {
  id: string
  asset_id: string
  timestamp: string
  event_type: TimelineEventType
  title: string
  description: string
  metadata: Record<string, unknown>
}

export interface DigitalTwinResponse {
  asset_id: string
  asset_name: string
  asset_type: string
  location: LocationResponse
  operational_state: OperationalStateResponse
  recommendation: RecommendationResponse
  notification: NotificationResponse | null
  investigation: InvestigationTransitionResponse | null
  latest_reasoning_run_id: string
  timeline_preview: TimelineEventResponse[]
  last_updated: string
}

