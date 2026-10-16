import { describe, expect, it } from 'vitest'
import { parseCompdocDashboard } from './compdocDashboard'
import { dashboardSummary } from '../models/compdocDashboard.fixtures'

describe('dashboard response validation', () => {
  it('retains project and panel analytics together', () => {
    const value = dashboardSummary()
    expect(parseCompdocDashboard(value)).toEqual(value)
  })

  it('accepts v2 very-high priorities with independent signal severity', () => {
    const value = dashboardSummary()
    Reflect.set(value.risk, 'counts', { very_high: 1, high: 0, medium: 0, low: 2 })
    Reflect.set(value.risk, 'policy', {
      version: 2,
      very_high_score: 90,
      high_score: 70,
      medium_score: 30,
      max_score: 100,
      priority_limit: 25
    })
    Reflect.set(value.risk.priorities[0], 'level', 'very_high')
    value.risk.priorities[0].score = 100
    value.risk.priorities[0].signals[0].severity = 'medium'
    expect(parseCompdocDashboard(value).risk).toEqual(value.risk)
    Reflect.set(value.risk.priorities[0].signals[0], 'severity', 'very_high')
    expect(() => parseCompdocDashboard(value)).toThrow('dashboard response is invalid')
  })

  it.each([
    (value: ReturnType<typeof dashboardSummary>) => {
      value.publication.not_issued.total = -1
    },
    (value: ReturnType<typeof dashboardSummary>) => {
      Reflect.set(value.panels[0].analytics.publication.issued, 'status_counts', null)
    },
    (value: ReturnType<typeof dashboardSummary>) => {
      value.panel_groups[0].analytics.unissued_moc_counts['1'] = -1
    },
    (value: ReturnType<typeof dashboardSummary>) => {
      Reflect.set(value.timeline, 'revised_scheduled', [{ x: '01.07.2026', y: -1 }])
    },
    (value: ReturnType<typeof dashboardSummary>) => {
      value.panel_groups[0].analytics.total = -1
    },
    (value: ReturnType<typeof dashboardSummary>) => {
      Reflect.set(value.panels[0].analytics.timeline, 'actual', null)
    },
    (value: ReturnType<typeof dashboardSummary>) => {
      value.pending_days.ubm = -1
    },
    (value: ReturnType<typeof dashboardSummary>) => {
      Reflect.set(value.risk.priorities[0].signals[0], 'points', '15')
    },
    (value: ReturnType<typeof dashboardSummary>) => {
      value.performance.actual.percentage = 101
    },
    (value: ReturnType<typeof dashboardSummary>) => {
      value.panels[0].analytics.risk.counts.high = NaN
    },
    (value: ReturnType<typeof dashboardSummary>) => {
      value.chart_status_counts.delayed = -1
    },
    (value: ReturnType<typeof dashboardSummary>) => {
      Reflect.set(value, 'cat_counts', { A: -1 })
    },
    (value: ReturnType<typeof dashboardSummary>) => {
      value.generated_at = 'yesterday'
    }
  ])('rejects malformed nested analytics', (corrupt) => {
    const value = dashboardSummary()
    corrupt(value)
    expect(() => parseCompdocDashboard(value)).toThrow('dashboard response is invalid')
  })
})
