import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'
import axios from 'axios'

const { confirmCompdocImport, previewCompdocImport } =
  await import('../src/services/compdocImports.ts')
const { shouldLoadCompdocHistory } = await import('../src/services/compdocHistory.ts')
const { fetchCompdocDashboard } = await import('../src/services/compdocDashboard.ts')

test('loads CompDoc history when list responses omit the lazy-loaded field', () => {
  assert.equal(shouldLoadCompdocHistory({ id: 'document-id' }, true), true)
  assert.equal(shouldLoadCompdocHistory({ id: 'document-id', history: null }, true), true)
  assert.equal(shouldLoadCompdocHistory({ id: 'document-id', history: [] }, true), false)
  assert.equal(shouldLoadCompdocHistory({ id: 'document-id' }, false), false)
  assert.equal(shouldLoadCompdocHistory({}, true), false)
})

test('preview requests persistence-free impact metadata', async () => {
  const captured = await captureRequest(
    () => previewCompdocImport('/ozgur/compdocs/upload/', workbook()),
    previewResponse()
  )

  assert.equal(captured.url, '/ozgur/compdocs/upload/?preview=true')
  assert.equal(captured.data.get('confirmation_token'), null)
  assert.equal(captured.data.get('file').name, 'compdocs.xlsx')
})

test('confirmation sends the signed decision with the exact file', async () => {
  const file = workbook()
  const captured = await captureRequest(
    () => confirmCompdocImport('/ozgur/compdocs/upload/', file, 'signed-preview'),
    { message: 'Imported', invalid_documents: [] }
  )

  assert.equal(captured.url, '/ozgur/compdocs/upload/?confirm_import=true')
  assert.equal(captured.data.get('confirmation_token'), 'signed-preview')
  assert.equal(captured.data.get('file'), file)
})

test('import UI refreshes database-conflicted previews without discarding the workbook', async () => {
  const [component, composable] = await Promise.all([
    readFile(new URL('../src/components/compdoc/UploadPopup.vue', import.meta.url), 'utf8'),
    readFile(new URL('../src/composables/useCompdocImport.ts', import.meta.url), 'utf8')
  ])

  assert.match(component, /previewNotice/)
  assert.match(component, /protected against concurrent database changes/)
  assert.match(composable, /COMPDOC_IMPORT_DATABASE_CONFLICT/)
  assert.match(composable, /COMPDOC_IMPORT_PREVIEW_EXPIRED/)
  assert.match(composable, /await loadPreview\(pendingFile\.value, true\)/)
  assert.doesNotMatch(composable, /finally[\s\S]{0,100}resetUploadState/)
})

test('CompDoc UI gates every mutation with project model permissions', async () => {
  const [table, toolbar, remoteTable, popup] = await Promise.all([
    readFile(new URL('../src/views/CompDocTable.vue', import.meta.url), 'utf8'),
    readFile(new URL('../src/components/compdoc/CompDocTableToolbar.vue', import.meta.url), 'utf8'),
    readFile(new URL('../src/composables/compdoc/remoteTable.ts', import.meta.url), 'utf8'),
    readFile(new URL('../src/components/compdoc/CompDocPopup.vue', import.meta.url), 'utf8')
  ])

  assert.match(table, /permission\('view'\)/)
  assert.match(table, /permission\('add'\)/)
  assert.match(table, /permission\('change'\)/)
  assert.match(table, /permission\('delete'\)/)
  assert.match(table, /hasEffectiveRole\(project\.value, `\$\{action\}_compdoc`\)/)
  assert.match(table, /v-if="canImport"/)
  assert.match(table, /:can-delete="canDelete"/)
  assert.match(toolbar, /v-if="canCreate"/)
  assert.match(toolbar, /v-if="canDelete"/)
  assert.match(remoteTable, /dependencies\.project\.value, dependencies\.canView\.value/)
  assert.match(popup, /popupMode == 'view' && canEdit/)
})

test('bulk delete requires the exact project phrase and reviewed server count', async () => {
  const [component, store] = await Promise.all([
    readFile(new URL('../src/components/compdoc/CompDocBulkDelete.vue', import.meta.url), 'utf8'),
    readFile(new URL('../src/stores/compdoc.ts', import.meta.url), 'utf8')
  ])

  assert.match(component, /DELETE \$\{props\.project\.toUpperCase\(\)\} COMPLIANCE DOCUMENTS/)
  assert.match(component, /expected_count: props\.count/)
  assert.match(store, /axios\.delete\([\s\S]*\{ data: payload \}/)
  assert.match(store, /pagination = \{ count: 0, next: null, previous: null \}/)
})

test('CompDoc table rejects stale project and list responses', async () => {
  const [store, organizations] = await Promise.all([
    readFile(new URL('../src/stores/compdoc.ts', import.meta.url), 'utf8'),
    readFile(new URL('../src/stores/organizationProjects.ts', import.meta.url), 'utf8')
  ])

  assert.match(store, /const requestedProject = this\.projectName/)
  assert.match(store, /const requestId = \+\+this\.listRequestId/)
  assert.match(store, /this\.projectName === requestedProject && this\.listRequestId === requestId/)
  assert.match(organizations, /if \(state\.project === requestedProject\) state\.panels = data/)
})

test('dashboard requests complete project analytics with cancellation support', async () => {
  const controller = new AbortController()
  const captured = await captureRequest(
    () => fetchCompdocDashboard('project name', controller.signal),
    dashboardResponse()
  )

  assert.equal(captured.url, '/project%20name/compdocs/dashboard/')
  assert.equal(captured.signal, controller.signal)
})

test('dashboard isolates paginated table state and stale project responses', async () => {
  const [home, composable, dashboard] = await Promise.all([
    readFile(new URL('../src/views/Home.vue', import.meta.url), 'utf8'),
    readFile(new URL('../src/composables/compdoc/dashboard.ts', import.meta.url), 'utf8'),
    readFile(new URL('../src/components/compdoc/ComplianceDashboard.vue', import.meta.url), 'utf8')
  ])

  assert.doesNotMatch(home, /fetchCompdocs|useCompdocStore/)
  assert.match(composable, /activeController\?\.abort\(\)/)
  assert.match(composable, /sequence === requestSequence/)
  assert.match(dashboard, /dataQualityIssues/)
  assert.match(dashboard, /invalid_status_flow/)
})

test('CompDoc charts use responsive modern Chart.js rendering paths', async () => {
  const [graph, status, timeline, legacyStore] = await Promise.all([
    readFile(new URL('../src/components/compdoc/Graph.vue', import.meta.url), 'utf8'),
    readFile(
      new URL('../src/components/compdoc/CompDocStatusDashboard.vue', import.meta.url),
      'utf8'
    ),
    readFile(
      new URL('../src/components/compdoc/CompDocTimelineDashboard.vue', import.meta.url),
      'utf8'
    ),
    readFile(new URL('../src/stores/chartStore.js', import.meta.url), 'utf8')
  ])

  assert.match(graph, /display-directive="if"/)
  assert.match(graph, /buildClientCompdocSummary/)
  assert.match(status, /createStatusChartData/)
  assert.match(timeline, /createTimelineChartData/)
  assert.doesNotMatch(legacyStore, /Outlabels|\$compdocStore/)
})

async function captureRequest(callback, responseData) {
  const originalAdapter = axios.defaults.adapter
  let captured
  axios.defaults.adapter = async (config) => {
    captured = config
    return { data: responseData, status: 200, statusText: 'OK', headers: {}, config }
  }
  try {
    await callback()
    return captured
  } finally {
    axios.defaults.adapter = originalAdapter
  }
}

function workbook() {
  return new File(['workbook'], 'compdocs.xlsx', {
    type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
  })
}

function previewResponse() {
  return {
    header_row: 1,
    mapped_columns: [],
    unmapped_columns: [],
    missing_columns: [],
    invalid_documents: [],
    created_count: 1,
    updated_count: 0,
    unchanged_count: 0,
    rejected_count: 0,
    confirmation_token: 'signed-preview',
    database_state_protected: true
  }
}

function dashboardResponse() {
  return {
    document_count: 0,
    status_counts: {},
    panels: [],
    pending_days: { authority: 0, ubm: 0, aw: 0 },
    timeline: { scheduled: [], actual: [], today: [], last_scheduled: null, last_actual: null },
    performance: {},
    data_quality: { issue_count: 0 },
    generated_at: new Date(0).toISOString()
  }
}
