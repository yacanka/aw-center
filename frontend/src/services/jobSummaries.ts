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

export interface DccCompdocRecommendation {
  id: string
  name: string
  panel: string
  ata: string
  status: string
  score: number
  reasons: string[]
}

export interface DccCompdocRefreshSummary {
  source_trace_id: string
  source_job_id: string
  document_count: number
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
  compliance_document_count?: number
  compliance_document_fingerprint?: string
  compliance_document_statuses?: Record<string, number>
  compliance_documents_without_technical_reference?: number
  readiness_score?: number
  readiness_level?: 'ready' | 'review'
  readiness_checks?: DccReadinessCheck[]
  readiness_warning_codes?: string[]
  requires_readiness_acknowledgement?: boolean
  compdoc_recommendations_available?: boolean
  compdoc_recommendation_project?: string
  compdoc_recommendation_count?: number
  compdoc_recommendations?: DccCompdocRecommendation[]
  compdoc_recommendation_candidates_truncated?: boolean
  compdoc_refresh?: DccCompdocRefreshSummary
}
