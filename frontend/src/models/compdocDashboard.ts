export interface DashboardPoint {
  x: string
  y: number
}

export interface DashboardMetric {
  filled: number
  empty: number
  percentage: number
}

export interface DashboardPanel {
  panel: string
  total: number
  [status: string]: string | number
}

export interface DashboardTimeline {
  scheduled: DashboardPoint[]
  actual: DashboardPoint[]
  today: DashboardPoint[]
  last_scheduled: DashboardPoint | null
  last_actual: DashboardPoint | null
}

export interface DashboardDataQuality {
  issue_count: number
  invalid_status_flow: number
  invalid_dates: number
  out_of_order_dates: number
  missing_panel: number
  unknown_status: number
}

export type DashboardRiskLevel = 'high' | 'medium' | 'low' | 'none'

export interface DashboardRiskSignal {
  code: string
  label: string
  points: number
  severity: Exclude<DashboardRiskLevel, 'none'>
  observed: number
  threshold: number
  unit: 'days' | 'cycles' | 'missing'
  detail: string
}

export interface DashboardRiskPriority {
  document_id: string
  name: string
  panel: string
  ata: string
  status: string
  stage_age_days: number
  score: number
  level: Exclude<DashboardRiskLevel, 'none'>
  signals: DashboardRiskSignal[]
}

export interface DashboardRiskPolicy {
  version: number
  high_score: number
  medium_score: number
  long_wait_days: number
  authority_aging_days: number
  max_score: number
  priority_limit: number
}

export interface DashboardRiskSummary {
  counts: Record<DashboardRiskLevel, number>
  at_risk_count: number
  average_score: number
  max_score: number
  priorities: DashboardRiskPriority[]
  policy: DashboardRiskPolicy
}

export interface CompDocDashboardSummary {
  document_count: number
  status_counts: Record<string, number>
  panels: DashboardPanel[]
  pending_days: Record<'authority' | 'ubm' | 'aw', number>
  timeline: DashboardTimeline
  performance: Record<'scheduled' | 'actual' | 'approved', DashboardMetric>
  risk: DashboardRiskSummary
  data_quality: DashboardDataQuality
  generated_at: string
}
