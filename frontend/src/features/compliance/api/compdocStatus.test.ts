import { expect, it } from 'vitest'
import { createEmptyCompdoc, statusColors } from './compdocCatalog'
import { withCompdocDisplayStatus } from './compdocStatus'
import { createStatusChartRows } from './compdocChartData'

it('displays In Design labels for unissued documents while retaining stored status codes', () => {
  const row = { ...createEmptyCompdoc(), status: 'to_be_issued', status_label: 'To be Issued' }
  const today = new Date(2026, 9, 13)
  expect(withCompdocDisplayStatus(row, today)).toMatchObject({
    status: 'to_be_issued',
    status_label: 'In Design (date missing)'
  })
  for (const date of ['2026-10-13', '2026-11-01']) {
    expect(withCompdocDisplayStatus({ ...row, target_date: date }, today)).toMatchObject({
      status: 'to_be_issued',
      status_label: 'In Design'
    })
  }
  expect(withCompdocDisplayStatus({ ...row, target_date: '2026-10-12' }, today)).toMatchObject({
    status: 'delayed',
    status_label: 'Delayed'
  })
  expect(
    withCompdocDisplayStatus(
      { ...row, target_date: '2026-01-01', revised_target_date: '2026-11-01' },
      today
    ).status_label
  ).toBe('In Design')
  expect(row.status_label).toBe('To be Issued')
})

it('uses the requested default labels and colors consistently in tables and charts', () => {
  const rows = createStatusChartRows(
    {
      expected: 1,
      missing_target: 1,
      airworthiness_review: 1,
      authority_review: 1,
      'to_be_re-submitted': 1,
      to_be_updated: 1
    },
    [{ value: 'airworthiness_review', label: 'Airworthiness Review' }]
  )
  expect(rows.find((row) => row.value === 'expected')?.label).toBe('In Design')
  expect(rows.find((row) => row.value === 'missing_target')?.label).toBe('In Design (date missing)')
  expect(rows.find((row) => row.value === 'airworthiness_review')?.label).toBe('Aw Review')
  expect(statusColors.airworthiness_review.color).toBe('#f97316')
  expect(statusColors.authority_review.color).toBe('#eab308')
  expect(statusColors['to_be_re-submitted'].color).toBe('#3b82f6')
  expect(statusColors.to_be_updated.color).toBe('#3b82f6')
  expect(statusColors.to_be_issued.color).toBe('#94a3b8')
  expect(statusColors.missing_target.color).toBe('#64748b')
})

it('preserves customized project labels for known default codes', () => {
  const row = {
    ...createEmptyCompdoc(),
    status: 'airworthiness_review',
    status_label: 'Project engineering gate'
  }
  expect(withCompdocDisplayStatus(row).status_label).toBe('Project engineering gate')
  expect(
    createStatusChartRows({ airworthiness_review: 1 }, [
      { value: 'airworthiness_review', label: 'Project engineering gate' }
    ])[0].label
  ).toBe('Project engineering gate')
})

it('uses the Istanbul calendar day across midnight regardless of browser timezone', () => {
  const row = { ...createEmptyCompdoc(), status: 'to_be_issued', target_date: '2026-10-13' }
  expect(withCompdocDisplayStatus(row, new Date('2026-10-13T22:00:00Z')).status).toBe('delayed')
})
