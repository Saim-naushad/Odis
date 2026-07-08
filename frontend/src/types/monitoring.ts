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

export interface DecisionPlanResponse extends DecisionPlanSummaryResponse {
  context_id: string
  created_at: string
  justification: string
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
}

