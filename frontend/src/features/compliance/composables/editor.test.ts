// @vitest-environment jsdom
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, h, ref } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { ICompDoc } from '@/features/compliance/models/compdocs'

const mocks = vi.hoisted(() => ({
  controller: {
    getProjectName: 'ozgur',
    checkBonusFields: vi.fn(),
    createCompdoc: vi.fn(),
    updateCompdoc: vi.fn(),
    acceptCreatedCompdoc: vi.fn(),
    acceptUpdatedCompdoc: vi.fn()
  },
  create: vi.fn(),
  options: vi.fn(),
  fetch: vi.fn(),
  existing: vi.fn(),
  resume: vi.fn()
}))
vi.mock('@/features/compliance/composables/compdocController', () => ({
  useCompdocController: () => mocks.controller
}))
vi.mock('@/features/compliance/api/compdocNumbering', () => ({
  createCoverPageAllocation: mocks.create,
  fetchNumberingOptions: mocks.options,
  fetchCoverPageAllocation: mocks.fetch,
  fetchExistingCoverPageAllocation: mocks.existing,
  resumeCoverPageAllocation: mocks.resume
}))
import { useCompDocEditor } from './editor'

describe('cover page numbering in the document editor', () => {
  const wrappers: ReturnType<typeof mount>[] = []
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.options.mockResolvedValue({ available: true, formats: ['COVER_PAGE', 'CP_ALT'] })
    mocks.existing.mockResolvedValue(null)
    mocks.create.mockResolvedValue({
      status: 'completed',
      number: 'CP-0001',
      document: { id: 'saved' }
    })
    window.$message = {
      success: vi.fn(),
      error: vi.fn(),
      info: vi.fn()
    } as unknown as typeof window.$message
  })
  afterEach(() => wrappers.splice(0).forEach((wrapper) => wrapper.unmount()))

  async function editor(mode = 'update', cover = '') {
    let state!: ReturnType<typeof useCompDocEditor>
    wrappers.push(
      mount(
        defineComponent({
          setup() {
            state = useCompDocEditor(ref(true))
            return () => h('div')
          }
        })
      )
    )
    state.openModal(
      {
        id: 'document-id',
        version: 4,
        name: 'Compliance document',
        cover_page_no: cover,
        cover_page_issue: 'A',
        cover_page_version: 2
      } as ICompDoc,
      mode
    )
    state.formRef.value = {
      validate: vi.fn().mockResolvedValue(undefined)
    } as unknown as NonNullable<typeof state.formRef.value>
    await flushPromises()
    return state
  }

  it('requires a format selection when several formats are allowed', async () => {
    const state = await editor()
    state.numberSource.value = 'numarator'
    await state.save()
    expect(mocks.create).not.toHaveBeenCalled()
    expect(window.$message.error).toHaveBeenCalledWith('Select a cover page number format.')
  })

  it('restores an unfinished allocation when the existing document is reopened', async () => {
    mocks.existing.mockResolvedValue({
      id: 'pending',
      format_code: 'CP_ALT',
      status: 'requested',
      job: { status: 'reconciliation_required' }
    })
    const state = await editor()
    expect(state.numberSource.value).toBe('numarator')
    expect(state.numberingFormat.value).toBe('CP_ALT')
    expect(state.allocationFailed.value).toBe(true)
    expect(state.formReadonly.value).toBe(true)
    expect(mocks.create).not.toHaveBeenCalled()
  })

  it('assigns an existing blank cover with selected format, document version and edited fields', async () => {
    const state = await editor()
    state.numberSource.value = 'numarator'
    state.numberingFormat.value = 'CP_ALT'
    state.compdoc.value.name = 'Edited name'
    await state.save()
    expect(mocks.create).toHaveBeenCalledWith(
      'ozgur',
      expect.any(String),
      expect.objectContaining({
        name: 'Edited name',
        version: 4,
        cover_page: { number: '', issue: 'A', version: 2 }
      }),
      'document-id',
      'CP_ALT'
    )
    expect(mocks.controller.updateCompdoc).not.toHaveBeenCalled()
    expect(mocks.controller.acceptUpdatedCompdoc).toHaveBeenCalledWith({ id: 'saved' })
    expect(state.showModal.value).toBe(false)
  })

  it('keeps manual updates and new-document numbering separate', async () => {
    const manual = await editor('update', 'MANUAL-1')
    await manual.save()
    expect(mocks.controller.updateCompdoc).toHaveBeenCalledOnce()
    const state = await editor('new')
    state.numberSource.value = 'numarator'
    state.numberingFormat.value = 'COVER_PAGE'
    await state.save()
    expect(mocks.create.mock.calls[0][2]).not.toHaveProperty('version')
    expect(mocks.create.mock.calls[0][3]).toBeUndefined()
    expect(mocks.controller.acceptCreatedCompdoc).toHaveBeenCalledOnce()
  })

  it('reuses the operation identity after a lost response', async () => {
    const state = await editor()
    state.numberSource.value = 'numarator'
    state.numberingFormat.value = 'COVER_PAGE'
    mocks.create.mockRejectedValueOnce(new Error('Connection lost'))
    await state.save()
    await state.save()
    expect(mocks.create.mock.calls[0]).toEqual(mocks.create.mock.calls[1])
  })

  it('does not submit a second allocation while the first is queued', async () => {
    const state = await editor()
    state.numberSource.value = 'numarator'
    state.numberingFormat.value = 'COVER_PAGE'
    mocks.create.mockResolvedValue({
      id: 'allocation',
      status: 'requested',
      job: { status: 'queued' }
    })
    await state.save()
    await state.save()
    expect(mocks.create).toHaveBeenCalledOnce()
  })

  it('resumes the same failed allocation and accepts the completed update', async () => {
    const state = await editor()
    state.numberSource.value = 'numarator'
    state.numberingFormat.value = 'COVER_PAGE'
    const failed = {
      id: 'allocation',
      version: 1,
      status: 'requested',
      job: { status: 'reconciliation_required' }
    }
    mocks.create.mockResolvedValue(failed)
    mocks.resume.mockResolvedValue({
      status: 'completed',
      number: 'CP-0001',
      document: { id: 'saved' }
    })
    await state.save()
    expect(state.allocationFailed.value).toBe(true)
    await state.retryAllocation()
    expect(mocks.resume).toHaveBeenCalledWith('ozgur', failed)
    expect(mocks.create).toHaveBeenCalledOnce()
    expect(mocks.controller.acceptUpdatedCompdoc).toHaveBeenCalledWith({ id: 'saved' })
  })
})
