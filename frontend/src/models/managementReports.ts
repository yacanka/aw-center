export interface ReportProjectOption {
  slug: string
  display_name: string
}

export interface ReportMetrics {
  document_count: number
  issued_count: number
  approved_count: number
  approval_percentage: number
  scheduled_count: number
  schedule_variance: number
  high_risk_count: number
  action_overdue_count: number
  action_due_soon_count: number
  unassigned_count: number
  pending_review_count: number
  pending_approval_count: number
  data_quality_issue_count: number
}

export interface ReportListItem {
  id: string
  title: string
  captured_at: string
  week_start: string
  schema_version: number
  project_slugs: string[]
}

export interface ProjectReportMetrics extends ReportMetrics, ReportProjectOption {}

export interface ReportPriority {
  document_id: string
  project_slug: string
  project_name: string
  name: string
  status: string
  score: number
  level: string
  stage_age_days: number
  reason: string
  owner: string | null
  next_action_due_date: string | null
}

export interface ManagementReport extends Omit<ReportListItem, 'id'> {
  id: string | null
  management_note: string
  totals: ReportMetrics
  projects: ProjectReportMetrics[]
  priorities: ReportPriority[]
}

export interface ReportComparison {
  available: boolean
  baseline: ReportListItem | null
  elapsed_days: number | null
  deltas: ReportMetrics | null
}

export interface ReportEnvelope {
  report: ManagementReport
  comparison: ReportComparison
}

export interface ReportPage {
  count: number
  next: string | null
  previous: string | null
  results: ReportListItem[]
}
