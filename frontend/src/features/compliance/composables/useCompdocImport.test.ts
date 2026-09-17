// @vitest-environment jsdom
import { effectScope } from 'vue'
import type { UploadCustomRequestOptions } from 'naive-ui'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { ImportPreview } from '../api/compdocImports'

const mocks = vi.hoisted(() => ({ preview: vi.fn(), confirm: vi.fn(), fetch: vi.fn() }))
vi.mock('../api/compdocImports', () => ({
  previewCompdocImport: mocks.preview,
  confirmCompdocImport: mocks.confirm
}))
vi.mock('./compdocController', () => ({
  useCompdocController: () => ({ fetchCompdocs: mocks.fetch })
}))
import { useCompdocImport } from './useCompdocImport'

const path = 'projects/ozgur/compliance-documents/'
const file = new File(['workbook'], 'documents.xlsx')
const result: ImportPreview = {
  header_row: 1,
  source_columns: ['Custom title'],
  target_fields: [{ key: 'name', label: 'Name', required: true }],
  mapped_columns: [{ source: 'Custom title', target: 'name' }],
  unmapped_columns: [],
  missing_columns: [],
  invalid_documents: [],
  created_count: 1,
  updated_count: 0,
  unchanged_count: 0,
  rejected_count: 0,
  confirmation_token: 'reviewed',
  database_state_protected: true
}
let scope: ReturnType<typeof effectScope>
function setup() {
  scope = effectScope()
  return scope.run(() => useCompdocImport(() => path))!
}
function upload() {
  return {
    file: { file },
    onFinish: vi.fn(),
    onError: vi.fn()
  } as unknown as UploadCustomRequestOptions
}

beforeEach(() => {
  vi.clearAllMocks()
  Object.assign(window, {
    $loadingBar: { start: vi.fn(), finish: vi.fn(), error: vi.fn() },
    $notification: { success: vi.fn(), error: vi.fn() }
  })
  mocks.preview.mockResolvedValue(result)
  mocks.confirm.mockResolvedValue({ detail: 'Imported', invalid_documents: [] })
})
afterEach(() => scope.stop())

describe('Excel linking preview workflow', () => {
  it('starts automatically, requires validation after edits, then confirms exact links', async () => {
    const flow = setup()
    await flow.handleUploadReq(upload())
    expect(mocks.preview).toHaveBeenLastCalledWith(path, file, undefined)
    expect(flow.showPreviewModal.value).toBe(true)
    expect(flow.canConfirm.value).toBe(true)
    flow.mode.value = 'manual'
    expect(flow.canConfirm.value).toBe(false)
    await flow.confirmImport()
    expect(mocks.confirm).not.toHaveBeenCalled()
    await flow.validateImport()
    expect(mocks.preview).toHaveBeenLastCalledWith(path, file, { 'Custom title': 'name' })
    expect(flow.canConfirm.value).toBe(true)
    flow.mapping.value = { 'Custom title': 'notes' }
    expect(flow.preview.value).toBeNull()
    expect(flow.canConfirm.value).toBe(false)
    flow.mapping.value = { 'Custom title': 'name' }
    await flow.validateImport()
    await flow.confirmImport()
    expect(mocks.confirm).toHaveBeenLastCalledWith(path, file, 'reviewed', {
      'Custom title': 'name'
    })
    expect(mocks.fetch).toHaveBeenCalledOnce()
    expect(flow.showPreviewModal.value).toBe(false)
  })

  it('opens failed automatic matching for manual recovery and clears preview on validation failure', async () => {
    mocks.preview.mockResolvedValueOnce({
      ...result,
      mapped_columns: [],
      missing_columns: ['name'],
      confirmation_token: ''
    })
    const flow = setup()
    await flow.handleUploadReq(upload())
    expect(flow.showPreviewModal.value).toBe(true)
    expect(flow.canConfirm.value).toBe(false)
    flow.mode.value = 'manual'
    flow.mapping.value = { 'Custom title': 'name' }
    await flow.validateImport()
    expect(flow.canConfirm.value).toBe(true)
    mocks.preview.mockRejectedValueOnce(new Error('Validation failed'))
    await flow.validateImport()
    expect(flow.preview.value).toBeNull()
    expect(flow.canConfirm.value).toBe(false)
    expect(flow.mapping.value).toEqual({ 'Custom title': 'name' })
  })

  it('does not restore stale validation and revalidates when returning to automatic mode', async () => {
    const flow = setup()
    await flow.handleUploadReq(upload())
    flow.mode.value = 'manual'
    let resolve!: (value: ImportPreview) => void
    mocks.preview.mockReturnValueOnce(
      new Promise<ImportPreview>((done) => {
        resolve = done
      })
    )
    const pending = flow.validateImport()
    flow.mapping.value = {}
    resolve(result)
    await pending
    expect(flow.canConfirm.value).toBe(false)
    flow.mode.value = 'automatic'
    await flow.validateImport()
    expect(mocks.preview).toHaveBeenLastCalledWith(path, file, undefined)
    expect(flow.canConfirm.value).toBe(true)
  })
})
