import { describe, expect, it } from 'vitest'
import { createTimelineChartData } from './compdocChartData'
import { createTimelineChartOptions } from './compdocChartAxisOptions'
import { dashboardAnalytics } from '../models/compdocDashboard.fixtures'

const stamp = (day: string) => new Date(`${day}T00:00:00`).getTime()

describe('daily burndown comparison', () => {
  it('holds the previous value on every intermediate day and aligns all series', () => {
    const timeline = {
      ...dashboardAnalytics().timeline,
      scheduled: [
        { x: '01.07.2026', y: 156 },
        { x: '05.07.2026', y: 152 }
      ],
      actual: [{ x: '03.07.2026', y: 158 }],
      revised_scheduled: [
        { x: '02.07.2026', y: 156 },
        { x: '06.07.2026', y: 152 }
      ],
      today: [{ x: '04.07.2026', y: 158 }]
    }
    const data = createTimelineChartData(timeline, 160)
    expect(data.datasets.map((row) => row.label)).toEqual([
      'Scheduled',
      'Actual',
      'Revised scheduled'
    ])
    const points = data.datasets.map((row) => row.data as Array<{ x: number; y: number }>)
    expect(points[0].map((point) => point.y)).toEqual([160, 156, 156, 156, 156, 152, 152])
    expect(points[1].map((point) => point.y)).toEqual([160, 160, 160, 158, 158, 158, 158])
    expect(points[2].map((point) => point.y)).toEqual([160, 160, 156, 156, 156, 156, 152])
    expect(points[0][4]).toEqual({ x: stamp('2026-07-04'), y: 156 })
    expect(points[1].map((point) => point.x)).toEqual(points[0].map((point) => point.x))
    expect(data.datasets.every((row) => row.stepped === 'before')).toBe(true)
    expect(createTimelineChartOptions('light', '04.07.2026', 160).interaction).toMatchObject({
      mode: 'index',
      intersect: false,
      axis: 'x'
    })
  })

  it('keeps an undelivered series at total and omits the revision legend when absent', () => {
    const timeline = { ...dashboardAnalytics().timeline, actual: [], revised_scheduled: [] }
    const data = createTimelineChartData(timeline, 3)
    expect(data.datasets.map((row) => row.label)).toEqual(['Scheduled', 'Actual'])
    expect(
      data.datasets[1].data.every((point) => typeof point === 'object' && point?.y === 3)
    ).toBe(true)
    expect(data.datasets[0].data.length).toBe(23)
  })
})

it('uses calendar days through daylight saving changes and combines same-day events', () => {
  const timeline = {
    ...dashboardAnalytics().timeline,
    scheduled: [
      { x: '24.10.2026', y: 2 },
      { x: '26.10.2026', y: 0 }
    ],
    actual: [{ x: '25.10.2026', y: 1 }],
    today: [{ x: '27.10.2026', y: 1 }]
  }
  const data = createTimelineChartData(timeline, 4)
  const points = data.datasets[0].data as Array<{ x: number; y: number }>
  expect(points.map((point) => new Date(point.x).getDate())).toEqual([23, 24, 25, 26, 27])
  expect(points.map((point) => point.y)).toEqual([4, 2, 2, 0, 0])
  expect(points.every((point) => new Date(point.x).getHours() === 0)).toBe(true)
})

it('handles empty timelines without inventing a revision series', () => {
  const data = createTimelineChartData(
    { scheduled: [], actual: [], today: [], last_actual: null, last_scheduled: null },
    0
  )
  expect(data.datasets.map((row) => row.data)).toEqual([[], []])
})
