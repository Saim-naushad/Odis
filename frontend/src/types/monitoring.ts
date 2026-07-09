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

export type TimelineEventType =
  | 'observation_received'
  | 'reasoning_started'
  | 'reasoning_completed'
  | 'recommendation_updated'
  | 'trend_changed'

export interface TimelineEventResponse {
  id: string
  asset_id: string
  timestamp: string
  event_type: TimelineEventType
  title: string
  description: string
  metadata: Record<string, unknown>
}

