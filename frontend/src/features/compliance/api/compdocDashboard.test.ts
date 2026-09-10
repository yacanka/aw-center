import { describe, expect, it } from 'vitest'
import { parseCompdocDashboard } from './compdocDashboard'
import { dashboardSummary } from '../models/compdocDashboard.fixtures'

describe('dashboard response validation', () => {
  it('retains project and panel analytics together', () => {
    const value = dashboardSummary()
    expect(parseCompdocDashboard(value)).toEqual(value)
  })

  it.each([
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
      value.generated_at = 'yesterday'
    }
  ])('rejects malformed nested analytics', (corrupt) => {
    const value = dashboardSummary()
    corrupt(value)
    expect(() => parseCompdocDashboard(value)).toThrow('dashboard response is invalid')
  })
})
