import assert from 'node:assert/strict'
import test from 'node:test'
import {
  getArrayFilterFunc,
  getBooleanFilterFunc,
  getDateFilterFunc,
  getStringFilterFunc
} from '../src/services/tableFilters.ts'
import { serializeCompdocFilters } from '../src/composables/compdoc/table.ts'
import {
  createDefaultColumnSettings,
  reconcileColumnSettings
} from '../src/services/compdocColumns.ts'
import { buildClientCompdocSummary } from '../src/services/compdocChartAlgorithms.ts'
import {
  createStatusChartData,
  createStatusChartRows,
  createTimelineChartData
} from '../src/services/compdocChartData.ts'

test('matches equal dates and supports both accepted date formats', () => {
  const filter = getDateFilterFunc('date')
  assert.equal(filter({ date: '19.07.2026', type: '==' }, { date: '2026-07-19' }), true)
  assert.equal(filter({ date: '19.07.2026', type: '!=' }, { date: '2026-07-19' }), false)
})

test('compares dates and fails closed for malformed values', () => {
  const filter = getDateFilterFunc('date')
  assert.equal(filter({ date: '18.07.2026', type: '>' }, { date: '2026-07-19' }), true)
  assert.equal(filter({ date: '20.07.2026', type: '<' }, { date: '2026-07-19' }), true)
  assert.equal(filter({ date: 'not-a-date', type: '==' }, { date: '2026-07-19' }), false)
})

test('handles string, boolean, and array cells without unsafe assumptions', () => {
  assert.equal(getStringFilterFunc('number')('23', { number: 1234 }), true)
  assert.equal(getBooleanFilterFunc('active')(true, { active: true }), true)
  assert.equal(getArrayFilterFunc('status')(['open'], { status: ['draft', 'open'] }), true)
  assert.equal(getArrayFilterFunc('status')([], { status: null }), true)
})

test('serializes remote date operators and multi-select filters', () => {
  assert.deepEqual(
    serializeCompdocFilters({
      panel: ['Systems', 'Structures'],
      ubm_target_date: { date: '19.07.2026', type: '>=' },
      empty: []
    }),
    {
      panel: ['Systems', 'Structures'],
      ubm_target_date__gte: '2026-07-19'
    }
  )
})

test('reconciles preferences with the current server field schema', () => {
  const fields = [
    field('name', true, 'text'),
    field('status', true, 'select'),
    field('notes', false, 'text')
  ]
  const settings = reconcileColumnSettings(
    [
      { key: 'removed', width: 10, sorter: true, filter: true, ellipsis: true },
      { key: 'name', width: 900, sorter: true, filter: true, ellipsis: false },
      { key: 'name', width: 100, sorter: true, filter: true, ellipsis: true }
    ],
    fields
  )

  assert.deepEqual(
    settings.map((setting) => setting.key),
    ['name', 'status']
  )
  assert.equal(settings[0].width, 600)
  assert.deepEqual(
    createDefaultColumnSettings(fields).map((setting) => setting.key),
    ['name', 'status']
  )
})

function field(key, defaultVisible, filterKind) {
  return {
    key,
    label: key,
    type: 'CharField',
    width: 160,
    filter_kind: filterKind,
    sortable: true,
    default_visible: defaultVisible,
    ellipsis: true,
    choices: [],
    option_source: null
  }
}

test('builds resilient CompDoc chart aggregates without changing status buckets', () => {
  const rows = [
    document('delayed', [{ status: 'to_be_issued', date: '20.07.2026' }]),
    document('authority_approved', [
      { status: 'to_be_issued', date: '01.07.2026' },
      { status: 'authority_review', date: '10.07.2026' },
      { status: 'authority_approved', date: '15.07.2026' }
    ]),
    document('to_be_updated', [{ status: 'to_be_updated', date: '18.07.2026' }]),
    document('unexpected', [{ status: 'to_be_issued', date: '31.02.2026' }])
  ]

  const summary = buildClientCompdocSummary(rows, new Date(2026, 6, 22))

  assert.equal(summary.statuses.delayed, 1)
  assert.equal(summary.statuses.authority_approved, 1)
  assert.equal(summary.statuses.unknown, 1)
  assert.deepEqual(summary.pendingDays, { authority: 5, ubm: 6, aw: 0 })
  assert.equal(summary.timeline.scheduled.length, 2)
})

test('creates zero-safe doughnut data and anchored stepped burndown lines', () => {
  const rows = createStatusChartRows({ to_be_issued: 3, authority_approved: 1, delayed: 0 })
  const statusData = createStatusChartData(rows)
  const timelineData = createTimelineChartData(
    {
      scheduled: [{ x: '20.07.2026', y: 3 }],
      actual: [{ x: '21.07.2026', y: 2 }],
      today: [{ x: '22.07.2026', y: 2 }],
      last_scheduled: null,
      last_actual: null
    },
    4
  )

  assert.deepEqual(statusData.datasets[0].data, [3, 1])
  assert.deepEqual(statusData.labels, ['To be Issued', 'Authority Approved'])
  assert.equal(timelineData.datasets[0].stepped, 'after')
  assert.equal(timelineData.datasets[0].data[0].y, 4)
  assert.equal(typeof timelineData.datasets[0].data[0].x, 'number')
})

function document(status, statusFlow) {
  return { status, status_flow: statusFlow }
}
