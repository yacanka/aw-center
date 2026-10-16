import { expect, it } from 'vitest'
import {
  createCatChartRows,
  createStatusChartData,
  createStatusChartRows
} from './compdocChartData'

it('omits zero status categories from both arcs and the visible distribution', () => {
  const counts = { authority_review: 0, custom: 2, unknown: 1 }
  const rows = createStatusChartRows(
    counts,
    [
      { value: 'authority_review', label: 'Authority Review' },
      { value: 'unused', label: 'Unused' },
      { value: 'custom', label: 'Project review' }
    ],
    '#888'
  )
  expect(rows.map((row) => [row.value, row.count, row.percentage])).toEqual([
    ['custom', 2, 67],
    ['unknown', 1, 33]
  ])
  expect(createStatusChartData(rows).labels).toEqual(['Project review', 'Unknown'])
  expect(counts).toEqual({ authority_review: 0, custom: 2, unknown: 1 })
})

it('omits zero CAT values while retaining positive unspecified values and ordering', () => {
  const rows = createCatChartRows({ A: 0, C: 2, B: 1, '': 1 }, ['red', 'blue'], 'gray')
  expect(rows.map((row) => [row.value, row.count, row.percentage])).toEqual([
    ['B', 1, 25],
    ['C', 2, 50],
    ['', 1, 25]
  ])
  expect(rows[2].label).toBe('Unspecified')
})

it('returns empty distributions for all-zero and empty inputs', () => {
  expect(createStatusChartRows({ unknown: 0 }, [{ value: 'unknown', label: 'Unknown' }])).toEqual(
    []
  )
  expect(createCatChartRows({ A: 0, '': 0 }, [], 'gray')).toEqual([])
  expect(createStatusChartData([]).datasets[0].data).toEqual([])
  expect(createStatusChartRows({})).toEqual([])
})
