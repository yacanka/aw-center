import assert from 'node:assert/strict'
import test from 'node:test'
import {
  normalizeReportScope,
  formatReportDelta,
  compatibleBaselines,
  createReportRequestGuard
} from '../src/services/managementReportHelpers.ts'

test('canonicalizes scope without silently introducing unauthorized projects', () => {
  assert.deepEqual(normalizeReportScope(['hys', 'ozgur', 'hys'], ['ozgur', 'hys']), [
    'hys',
    'ozgur'
  ])
  assert.throws(() => normalizeReportScope(['unknown'], ['ozgur']), /authorized/)
  assert.throws(() => normalizeReportScope([], ['ozgur']), /Select/)
})

test('keeps missing baseline distinct from a zero net change and labels percentage points', () => {
  assert.equal(formatReportDelta(null), '—')
  assert.equal(formatReportDelta(0), '0')
  assert.equal(formatReportDelta(3), '+3')
  assert.equal(formatReportDelta(-1.2, true), '-1.2 pp')
})

test('offers only older identical-scope/schema snapshots for explicit baseline', () => {
  const current = {
    id: 'current',
    captured_at: '2026-10-27T12:00:00Z',
    schema_version: 1,
    project_slugs: ['ozgur', 'hys']
  }
  const baseline = {
    id: 'old',
    captured_at: '2026-10-20T12:00:00Z',
    schema_version: 1,
    project_slugs: ['hys', 'ozgur']
  }
  assert.deepEqual(
    compatibleBaselines(
      [
        baseline,
        current,
        { ...baseline, id: 'scope', project_slugs: ['ozgur'] },
        { ...baseline, id: 'schema', schema_version: 2 }
      ],
      current
    ),
    [baseline]
  )
})

test('invalidates slow scope/report responses and aborts superseded requests', () => {
  const guard = createReportRequestGuard()
  const first = guard.begin()
  const second = guard.begin()
  assert.equal(first.signal.aborted, true)
  assert.equal(first.isCurrent(), false)
  assert.equal(second.isCurrent(), true)
  guard.cancel()
  assert.equal(second.signal.aborted, true)
  assert.equal(second.isCurrent(), false)
})

test('report transport submits only editable fields and downloads a saved UUID with baseline', async () => {
  const { default: axios } = await import('axios')
  const api = await import('../src/services/managementReports.ts')
  const originalGet = axios.get
  const originalPost = axios.post
  const calls = []
  const controller = new AbortController()
  axios.get = async (...args) => {
    calls.push(['get', ...args])
    return { data: args[0].endsWith('options/') ? { projects: [] } : new Blob(['pdf']) }
  }
  axios.post = async (...args) => {
    calls.push(['post', ...args])
    return { data: { report: { id: 'saved' } } }
  }
  try {
    assert.deepEqual(await api.fetchReportOptions(controller.signal), [])
    await api.captureReport(['ozgur'], 'Weekly', 'Context', controller.signal)
    await api.downloadReportPdf('saved/uuid', 'baseline', controller.signal)
    assert.deepEqual(calls[1], [
      'post',
      '/management-reports/reports/',
      { project_slugs: ['ozgur'], title: 'Weekly', management_note: 'Context' },
      { signal: controller.signal }
    ])
    assert.deepEqual(calls[2], [
      'get',
      '/management-reports/reports/saved%2Fuuid/pdf/',
      { params: { baseline: 'baseline' }, responseType: 'blob', signal: controller.signal }
    ])
  } finally {
    axios.get = originalGet
    axios.post = originalPost
  }
})

test('a late network completion cannot replace the report for the new scope', async () => {
  const guard = createReportRequestGuard()
  let rendered = null
  let finishOld
  const oldResponse = new Promise((resolve) => {
    finishOld = resolve
  })
  const first = guard.begin()
  const firstRender = oldResponse.then((value) => {
    if (first.isCurrent()) rendered = value
  })
  const second = guard.begin()
  if (second.isCurrent()) rendered = { project: 'hys', savedId: 'new-report' }
  finishOld({ project: 'ozgur', savedId: 'old-report' })
  await firstRender
  assert.deepEqual(rendered, { project: 'hys', savedId: 'new-report' })
})

test('PDF JSON Blob failures preserve the API error contract and diagnostic reference', async () => {
  const { default: axios } = await import('axios')
  const { downloadReportPdf } = await import('../src/services/managementReports.ts')
  const { formatApiError, getApiErrorCode } = await import('../src/services/apiError.ts')
  const payload = {
    detail: 'Project access was revoked.',
    code: 'permission_denied',
    request_id: 'report-request-42'
  }
  const failure = new axios.AxiosError('Request failed with status code 403')
  failure.response = {
    status: 403,
    data: new Blob([JSON.stringify(payload)], { type: 'application/json' })
  }
  const originalGet = axios.get
  axios.get = async () => {
    throw failure
  }
  try {
    await assert.rejects(downloadReportPdf('saved'), (error) => {
      assert.equal(error, failure)
      assert.equal(error.response.status, 403)
      assert.deepEqual(error.response.data, payload)
      assert.equal(getApiErrorCode(error), 'permission_denied')
      assert.equal(
        formatApiError(error),
        'Project access was revoked.\nReference: report-request-42'
      )
      return true
    })
  } finally {
    axios.get = originalGet
  }
})

test('non-JSON PDF errors retain the original error and safe fallback', async () => {
  const { default: axios } = await import('axios')
  const { downloadReportPdf } = await import('../src/services/managementReports.ts')
  const { formatApiError, FALLBACK_ERROR_MESSAGE } = await import('../src/services/apiError.ts')
  const failure = new axios.AxiosError('Request failed with status code 502')
  const body = new Blob(['<html>upstream failure</html>'], { type: 'text/html' })
  failure.response = { status: 502, data: body }
  const originalGet = axios.get
  axios.get = async () => {
    throw failure
  }
  try {
    await assert.rejects(downloadReportPdf('saved'), (error) => {
      assert.equal(error, failure)
      assert.equal(error.response.data, body)
      assert.equal(formatApiError(error), FALLBACK_ERROR_MESSAGE)
      return true
    })
  } finally {
    axios.get = originalGet
  }
})
