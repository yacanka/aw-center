// @vitest-environment jsdom
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, h, ref } from 'vue'
import { NForm, NFormItem } from 'naive-ui'
import type { FormInst } from 'naive-ui'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { ICompDoc } from '@/features/compliance/models/compdocs'
import { RequestError } from '@/shared/composables/promise'

const mocks = vi.hoisted(() => ({
  controller: {
    getProjectName: 'ozgur',
    createCompdoc: vi.fn(),
    updateCompdoc: vi.fn(),
    fetchCompdoc: vi.fn(),
    acceptCreatedCompdoc: vi.fn(),
    acceptUpdatedCompdoc: vi.fn()
  },
  create: vi.fn(),
  options: vi.fn(),
  format: vi.fn(),
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
  fetchNumberingFormat: mocks.format,
  fetchCoverPageAllocation: mocks.fetch,
  fetchExistingCoverPageAllocation: mocks.existing,
  resumeCoverPageAllocation: mocks.resume
}))
import { useCompDocEditor } from './editor'

describe('cover page numbering in the document editor', () => {
  const wrappers: ReturnType<typeof mount>[] = []
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.fetch.mockReset()
    mocks.resume.mockReset()
    mocks.controller.updateCompdoc.mockResolvedValue(undefined)
    mocks.options.mockResolvedValue({ available: true, formats: ['COVER_PAGE', 'CP_ALT'] })
    mocks.format.mockImplementation(async (_project, code) => ({ code, fields: [] }))
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
    window.$dialog = { warning: vi.fn() } as unknown as typeof window.$dialog
  })
  afterEach(() => {
    wrappers.splice(0).forEach((wrapper) => wrapper.unmount())
    vi.useRealTimers()
  })

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

  it('rejects blank identity and accepts optional metadata or a generated cover', async () => {
    const state = await editor('new')
    const form = ref<FormInst | null>(null)
    wrappers.push(
      mount(
        defineComponent({
          setup: () => () =>
            h(
              NForm,
              {
                ref: form,
                model: state.compdoc.value,
                rules: state.rules.value
              },
              {
                default: () => [
                  h(NFormItem, { path: 'name' }),
                  h(NFormItem, { path: 'cover_page_no' })
                ]
              }
            )
        })
      )
    )
    await expect(form.value!.validate()).rejects.toBeDefined()
    state.compdoc.value.cover_page_no = 'CP-1'
    state.compdoc.value.name = '   '
    await flushPromises()
    await expect(form.value!.validate()).rejects.toBeDefined()
    state.compdoc.value.name = 'Document'
    state.compdoc.value.cover_page_no = '   '
    await flushPromises()
    await expect(form.value!.validate()).rejects.toBeDefined()
    state.compdoc.value.cover_page_no = 'CP-1'
    await flushPromises()
    await expect(form.value!.validate()).resolves.toBeDefined()
    state.compdoc.value.cover_page_no = ''
    state.numberSource.value = 'numarator'
    await flushPromises()
    await expect(form.value!.validate()).resolves.toBeDefined()
  })

  it('requires a format selection when several formats are allowed', async () => {
    const state = await editor()
    state.numberSource.value = 'numarator'
    await flushPromises()
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
    await flushPromises()
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
      'CP_ALT',
      {}
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
    await flushPromises()
    await state.save()
    expect(mocks.create.mock.calls[0][2]).not.toHaveProperty('version')
    expect(mocks.create.mock.calls[0][3]).toBeUndefined()
    expect(mocks.controller.acceptCreatedCompdoc).toHaveBeenCalledOnce()
  })

  it('refreshes the matching cover version while retaining the user draft after a conflict', async () => {
    const state = await editor('update', 'MANUAL-1')
    state.compdoc.value.name = 'My unsaved name'
    state.compdoc.value.cover_page_issue = 'C'
    mocks.controller.updateCompdoc.mockRejectedValueOnce(
      new RequestError('Cover changed', 409, 'COVER_PAGE_VERSION_CONFLICT')
    )
    mocks.controller.fetchCompdoc.mockResolvedValue({
      ...state.originalCompdoc.value,
      version: 5,
      cover_page_issue: 'B',
      cover_page_version: 3
    })

    await state.save()
    await vi
      .mocked(window.$dialog.warning)
      .mock.calls[0][0].onPositiveClick?.(new MouseEvent('click'))
    await state.save()

    expect(mocks.controller.updateCompdoc).toHaveBeenLastCalledWith(
      'document-id',
      expect.objectContaining({
        version: 5,
        name: 'My unsaved name',
        cover_page: { number: 'MANUAL-1', issue: 'C', version: 3 }
      })
    )
    expect(state.originalCompdoc.value.cover_page_issue).toBe('B')
  })

  it.each(['different document', 'same document', 'unmount'])(
    'ignores a conflict reload after opening a new editor session: %s',
    async (scenario) => {
      const state = await editor('update', 'MANUAL-1')
      const original = { ...state.compdoc.value }
      mocks.controller.updateCompdoc.mockRejectedValueOnce(
        new RequestError('Document changed', 409)
      )
      let resolve!: (value: ICompDoc) => void
      mocks.controller.fetchCompdoc.mockReturnValueOnce(
        new Promise<ICompDoc>((done) => {
          resolve = done
        })
      )
      await state.save()
      const pending = vi
        .mocked(window.$dialog.warning)
        .mock.calls[0][0].onPositiveClick?.(new MouseEvent('click'))
      if (scenario === 'unmount') wrappers[0].unmount()
      else
        state.openModal(
          {
            ...original,
            id: scenario === 'same document' ? original.id : 'other-id',
            name: 'Reopened draft'
          },
          'update'
        )
      const before = JSON.parse(JSON.stringify(state.compdoc.value))
      const baseline = JSON.parse(JSON.stringify(state.originalCompdoc.value))
      resolve({ ...original, version: 50, cover_page_version: 30 })
      await pending
      expect(state.compdoc.value).toEqual(before)
      expect(state.originalCompdoc.value).toEqual(baseline)
      expect(window.$message.info).not.toHaveBeenCalled()
    }
  )

  it('ignores a conflict dialog confirmation belonging to a previous editor session', async () => {
    const state = await editor('update', 'MANUAL-1')
    mocks.controller.updateCompdoc.mockRejectedValueOnce(new RequestError('Document changed', 409))
    await state.save()
    const confirm = vi.mocked(window.$dialog.warning).mock.calls[0][0].onPositiveClick
    state.openModal({ ...state.compdoc.value, name: 'Reopened draft' }, 'update')
    const previousCalls = mocks.controller.fetchCompdoc.mock.calls.length
    await confirm?.(new MouseEvent('click'))
    expect(mocks.controller.fetchCompdoc.mock.calls).toHaveLength(previousCalls)
    expect(state.compdoc.value.name).toBe('Reopened draft')
  })

  it('does not attach another cover version to a new cover number during conflict reload', async () => {
    const state = await editor('update', 'MANUAL-1')
    state.compdoc.value.cover_page_no = 'NEW-COVER'
    state.compdoc.value.cover_page_issue = 'C'
    mocks.controller.updateCompdoc.mockRejectedValueOnce(new RequestError('Document changed', 409))
    mocks.controller.fetchCompdoc.mockResolvedValue({
      ...state.originalCompdoc.value,
      version: 5,
      cover_page_issue: 'B',
      cover_page_version: 3
    })

    await state.save()
    await vi
      .mocked(window.$dialog.warning)
      .mock.calls[0][0].onPositiveClick?.(new MouseEvent('click'))
    await state.save()

    expect(mocks.controller.updateCompdoc).toHaveBeenLastCalledWith(
      'document-id',
      expect.objectContaining({
        version: 5,
        cover_page: { number: 'NEW-COVER', issue: 'C' }
      })
    )
    expect(state.compdoc.value.cover_page_no).toBe('NEW-COVER')
  })

  it('reuses the operation identity after a lost response', async () => {
    const state = await editor()
    state.numberSource.value = 'numarator'
    state.numberingFormat.value = 'COVER_PAGE'
    mocks.create.mockRejectedValueOnce(new Error('Connection lost'))
    await flushPromises()
    await state.save()
    await flushPromises()
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
    await flushPromises()
    await state.save()
    await flushPromises()
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
    await flushPromises()
    await state.save()
    expect(state.allocationFailed.value).toBe(true)
    await state.retryAllocation()
    expect(mocks.resume).toHaveBeenCalledWith('ozgur', failed)
    expect(mocks.create).toHaveBeenCalledOnce()
    expect(mocks.controller.acceptUpdatedCompdoc).toHaveBeenCalledWith({ id: 'saved' })
  })
  it('asks for custom format values and sends them with a single-document request', async () => {
    mocks.format.mockResolvedValue({
      code: 'CP_ALT',
      fields: [{ key: 'department', required: true, default: null, max_length: 10 }]
    })
    const state = await editor()
    state.numberSource.value = 'numarator'
    state.numberingFormat.value = 'CP_ALT'
    await flushPromises()
    await state.save()
    expect(mocks.create).not.toHaveBeenCalled()
    state.numberingContext.values.value.department = 'ENG'
    await state.save()
    expect(mocks.create.mock.calls[0][5]).toEqual({ department: 'ENG' })
  })

  it('lets the user reload a failed poll without allocating another number', async () => {
    vi.useFakeTimers()
    mocks.existing.mockResolvedValue({
      id: 'pending-allocation',
      format_code: 'COVER_PAGE',
      status: 'requested',
      job: { status: 'queued' }
    })
    mocks.fetch.mockRejectedValueOnce(new Error('Temporary network failure'))
    const state = await editor()
    await vi.advanceTimersByTimeAsync(1500)
    expect(state.allocationFailed.value).toBe(true)
    expect(state.allocationActive.value).toBe(false)
    mocks.fetch.mockResolvedValue({
      id: 'pending-allocation',
      status: 'completed',
      number: 'CP-1',
      document: { id: 'saved' }
    })
    await state.retryAllocation()
    expect(state.showModal.value).toBe(false)
    expect(mocks.fetch).toHaveBeenLastCalledWith('ozgur', 'pending-allocation')
    expect(mocks.resume).not.toHaveBeenCalled()
    expect(mocks.create).not.toHaveBeenCalled()
  })

  it('offers retry for a cancelled allocation and resumes its identity', async () => {
    const cancelled = {
      id: 'cancelled-allocation',
      version: 1,
      format_code: 'COVER_PAGE',
      status: 'requested',
      job: { status: 'cancelled' }
    }
    mocks.existing.mockResolvedValue(cancelled)
    const state = await editor()
    expect(state.allocationFailed.value).toBe(true)
    mocks.resume.mockResolvedValue({
      id: cancelled.id,
      status: 'completed',
      number: 'CP-1',
      document: { id: 'saved' }
    })
    await state.retryAllocation()
    expect(state.showModal.value).toBe(false)
    expect(mocks.resume).toHaveBeenCalledWith('ozgur', cancelled)
    expect(mocks.create).not.toHaveBeenCalled()
  })

  it('reloads the same allocation after a lost resume response', async () => {
    const failed = {
      id: 'failed-allocation',
      version: 1,
      format_code: 'COVER_PAGE',
      status: 'requested',
      job: { status: 'failed' }
    }
    mocks.existing.mockResolvedValue(failed)
    mocks.resume.mockRejectedValue(new Error('Resume response lost'))
    const state = await editor()
    await state.retryAllocation()
    mocks.fetch.mockResolvedValue({
      id: failed.id,
      status: 'completed',
      number: 'CP-1',
      document: { id: 'saved' }
    })
    await state.retryAllocation()
    expect(state.showModal.value).toBe(false)
    expect(mocks.resume).toHaveBeenCalledOnce()
    expect(mocks.fetch).toHaveBeenCalledWith('ozgur', failed.id)
    expect(mocks.create).not.toHaveBeenCalled()
  })

  it.each(['reopen', 'unmount'])('ignores a completed poll after %s', async (scenario) => {
    vi.useFakeTimers()
    mocks.existing.mockResolvedValue({
      id: 'pending-allocation',
      format_code: 'COVER_PAGE',
      status: 'requested',
      job: { status: 'queued' }
    })
    let resolve!: (value: unknown) => void
    mocks.fetch.mockReturnValue(
      new Promise((done) => {
        resolve = done
      })
    )
    const state = await editor()
    await vi.advanceTimersByTimeAsync(1500)
    if (scenario === 'unmount') wrappers[0].unmount()
    else {
      mocks.existing.mockResolvedValue(null)
      state.openModal(
        { id: 'another', name: 'Another draft', cover_page_no: 'CP-2' } as ICompDoc,
        'update'
      )
      await flushPromises()
    }
    resolve({ status: 'completed', number: 'CP-1', document: { id: 'saved' } })
    await flushPromises()
    expect(mocks.controller.acceptUpdatedCompdoc).not.toHaveBeenCalled()
    expect(window.$message.success).not.toHaveBeenCalled()
    if (scenario === 'reopen') expect(state.showModal.value).toBe(true)
  })

  it('does not restart allocation polling when an enqueue response arrives after unmount', async () => {
    vi.useFakeTimers()
    let resolve!: (value: unknown) => void
    mocks.create.mockReturnValue(
      new Promise((done) => {
        resolve = done
      })
    )
    const state = await editor()
    state.numberSource.value = 'numarator'
    state.numberingFormat.value = 'COVER_PAGE'
    await flushPromises()
    const saving = state.save()
    await flushPromises()
    wrappers[0].unmount()
    resolve({ id: 'pending', status: 'requested', job: { status: 'queued' } })
    await saving
    await vi.advanceTimersByTimeAsync(1500)
    expect(mocks.fetch).not.toHaveBeenCalled()
  })

  it('does not poll a terminal allocation after loading it', async () => {
    vi.useFakeTimers()
    mocks.existing.mockResolvedValue({
      id: 'cancelled-allocation',
      format_code: 'COVER_PAGE',
      status: 'requested',
      job: { status: 'cancelled' }
    })
    const state = await editor()
    await vi.advanceTimersByTimeAsync(1500)
    expect(state.allocationFailed.value).toBe(true)
    expect(mocks.fetch).not.toHaveBeenCalled()
  })

  it('keeps another draft open when an earlier allocation resume completes', async () => {
    mocks.existing.mockResolvedValue({
      id: 'cancelled-allocation',
      format_code: 'COVER_PAGE',
      status: 'requested',
      job: { status: 'cancelled' }
    })
    const state = await editor()
    let resolve!: (value: unknown) => void
    mocks.resume.mockReturnValue(
      new Promise((done) => {
        resolve = done
      })
    )
    const retrying = state.retryAllocation()
    mocks.existing.mockResolvedValue(null)
    state.openModal(
      { id: 'another', name: 'Another draft', cover_page_no: 'CP-2' } as ICompDoc,
      'update'
    )
    await flushPromises()
    resolve({ status: 'completed', number: 'CP-1', document: { id: 'saved' } })
    await retrying
    expect(state.showModal.value).toBe(true)
    expect(state.compdoc.value.id).toBe('another')
    expect(mocks.controller.acceptUpdatedCompdoc).not.toHaveBeenCalled()
  })
})
