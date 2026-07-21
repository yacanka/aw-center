import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'
import axios from 'axios'

const { confirmCompdocImport, previewCompdocImport } =
  await import('../src/services/compdocImports.ts')
const { shouldLoadCompdocHistory } = await import('../src/services/compdocHistory.ts')

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
  const [table, popup] = await Promise.all([
    readFile(new URL('../src/views/CompDocTable.vue', import.meta.url), 'utf8'),
    readFile(new URL('../src/components/compdoc/CompDocPopup.vue', import.meta.url), 'utf8')
  ])

  assert.match(table, /'view_compdoc'/)
  assert.match(table, /'add_compdoc'/)
  assert.match(table, /'change_compdoc'/)
  assert.match(table, /'delete_compdoc'/)
  assert.match(table, /v-if="canImport"/)
  assert.match(table, /v-if="canCreate"/)
  assert.match(table, /v-if="canDelete"/)
  assert.match(table, /\[route\.params\.project, canView\.value\]/)
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
