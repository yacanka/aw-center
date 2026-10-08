import { expect, it } from 'vitest'
import { buildClientCompdocSummary } from './compdocChartAlgorithms'
import { createEmptyCompdoc } from './compdocCatalog'

it('keeps table burndown dates consistent with the dashboard including future deliveries', () => {
  const first = {
    ...createEmptyCompdoc(),
    ubm_target_date: '01.07.2026',
    ubm_revised_target_date: '01.08.2026',
    ubm_delivery_date: '02.08.2026'
  }
  const second = { ...createEmptyCompdoc(), ubm_target_date: '03.07.2026' }
  const { timeline } = buildClientCompdocSummary([first, second], new Date(2026, 6, 22))
  expect(timeline.scheduled).toEqual([
    { x: '01.07.2026', y: 1 },
    { x: '03.07.2026', y: 0 }
  ])
  expect(timeline.revised_scheduled).toEqual([
    { x: '03.07.2026', y: 1 },
    { x: '01.08.2026', y: 0 }
  ])
  expect(timeline.actual).toEqual([
    { x: '22.07.2026', y: 2 },
    { x: '02.08.2026', y: 1 }
  ])
})
