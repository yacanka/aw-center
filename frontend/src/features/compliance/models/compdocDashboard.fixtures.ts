import type { CompDocDashboardSummary, DashboardAnalytics } from './compdocDashboard'

/** Synthetic analytics shared by dashboard regression tests. */
export function dashboardAnalytics(total = 3, pending = 20): DashboardAnalytics {
  return {
    total,
    overdue: 0,
    status_counts: { to_be_issued: total },
    chart_status_counts: { delayed: total },
    pending_days: { authority: 0, ubm: pending, aw: 0 },
    timeline: {
      scheduled: [{ x: '01.07.2026', y: 0 }],
      actual: [{ x: '22.07.2026', y: total }],
      today: [{ x: '22.07.2026', y: total }],
      last_scheduled: { x: '01.07.2026', y: 0 },
      last_actual: null
    },
    performance: {
      scheduled: { filled: total, empty: 0, percentage: 100 },
      actual: { filled: 0, empty: total, percentage: 0 },
      approved: { filled: 0, empty: total, percentage: 0 }
    },
    risk: {
      counts: { high: 0, medium: 0, low: total, none: 0 },
      at_risk_count: total,
      average_score: 15,
      max_score: 15,
      priorities: [
        {
          document_id: `00000000-0000-4000-8000-00000000000${total}`,
          name: 'Synthetic overdue document',
          panel: 'Systems',
          ata: '27',
          status: 'delayed',
          stage_age_days: 1,
          score: 15,
          level: 'low',
          signals: [
            {
              code: 'sla_target_overdue',
              label: 'SLA target overdue',
              points: 15,
              severity: 'medium',
              observed: 1,
              threshold: 0,
              unit: 'days',
              detail: 'UBM target is 1 day overdue.'
            }
          ]
        }
      ],
      policy: {
        version: 1,
        high_score: 60,
        medium_score: 30,
        long_wait_days: 30,
        authority_aging_days: 14,
        max_score: 100,
        priority_limit: 25
      }
    },
    data_quality: {
      issue_count: 0,
      missing_panel: 0,
      unknown_status: 0,
      blank_cover_page: 0,
      out_of_order_dates: 0
    }
  }
}

export function dashboardSummary(project = 'ozgur'): CompDocDashboardSummary {
  return {
    ...dashboardAnalytics(),
    project,
    archived: 2,
    generated_at: '2026-07-22T12:00:00Z',
    panels: [
      { id: 'panel-1', panel: 'Systems', ata: '27', analytics: dashboardAnalytics(1, 3) },
      { id: 'panel-2', panel: 'Systems', ata: '28', analytics: dashboardAnalytics(2, 17) }
    ]
  }
}
