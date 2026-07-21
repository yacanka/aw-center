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

export interface CompDocDashboardSummary {
  document_count: number
  status_counts: Record<string, number>
  panels: DashboardPanel[]
  pending_days: Record<'authority' | 'ubm' | 'aw', number>
  timeline: DashboardTimeline
  performance: Record<'scheduled' | 'actual' | 'approved', DashboardMetric>
  data_quality: DashboardDataQuality
  generated_at: string
}
