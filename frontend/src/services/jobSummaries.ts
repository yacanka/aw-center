export interface AnalysisCheckSummary {
  id: string
  title: string
  score: number
  status: 'success' | 'warning' | 'error'
}

export interface DccReadinessCheck {
  code: string
  title: string
  status: 'success' | 'warning' | 'info'
  detail: string
  recovery_hint: string
}

export interface JobResultSummary {
  type?: string
  issue_key?: string
  project?: string
  overall_score?: number
  passed?: number
  total?: number
  checks?: AnalysisCheckSummary[]
  output_name?: string
  panel_count?: number
  template_ready?: boolean
  source_updated_at?: string
  missing_recommended_fields?: string[]
  warning_count?: number
  readiness_score?: number
  readiness_level?: 'ready' | 'review'
  readiness_checks?: DccReadinessCheck[]
  readiness_warning_codes?: string[]
  requires_readiness_acknowledgement?: boolean
}
