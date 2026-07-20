import assert from 'node:assert/strict'
import test from 'node:test'
import axios from 'axios'

const { confirmCompdocImport, previewCompdocImport } =
  await import('../src/services/compdocImports.ts')

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
    confirmation_token: 'signed-preview'
  }
}
