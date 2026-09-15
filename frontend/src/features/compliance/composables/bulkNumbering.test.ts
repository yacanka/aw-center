// @vitest-environment jsdom
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, h, ref } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createEmptyCompdoc } from '../api/compdocCatalog'
const mocks = vi.hoisted(() => ({
  options: vi.fn(),
  format: vi.fn(),
  create: vi.fn(),
  existing: vi.fn(),
  fetch: vi.fn(),
  resume: vi.fn(),
  accept: vi.fn()
}))
vi.mock('../api/compdocNumbering', () => ({
  fetchNumberingOptions: mocks.options,
  fetchNumberingFormat: mocks.format,
  createCoverPageAllocation: mocks.create,
  fetchExistingCoverPageAllocation: mocks.existing,
  fetchCoverPageAllocation: mocks.fetch,
  resumeCoverPageAllocation: mocks.resume
}))
import { useBulkNumbering } from './bulkNumbering'

describe('bulk cover page numbering', () => {
  const wrappers: ReturnType<typeof mount>[] = []
  const queued = {
    id: 'allocation-1',
    version: 1,
    status: 'requested',
    format_code: 'CP',
    job: { status: 'queued' }
  }
  beforeEach(() => {
    vi.resetAllMocks()
    vi.useFakeTimers()
    mocks.options.mockResolvedValue({ available: true, formats: ['CP'] })
    mocks.format.mockImplementation(async (_project, code) => ({
      code,
      fields: [],
      schema_version: 1
    }))
    mocks.existing.mockResolvedValue(null)
    mocks.create.mockResolvedValue(queued)
    mocks.fetch.mockResolvedValue(queued)
  })
  afterEach(() => {
    wrappers.splice(0).forEach((wrapper) => wrapper.unmount())
    vi.useRealTimers()
  })
  const document = (id: string) => ({
    ...createEmptyCompdoc(),
    id,
    name: id,
    version: 3,
    cover_page_version: 2
  })
  let page = ref([document('first'), document('second')])
  async function setup(edit = true) {
    page = ref([document('first'), document('second')])
    let state!: ReturnType<typeof useBulkNumbering>
    wrappers.push(
      mount(
        defineComponent({
          setup() {
            state = useBulkNumbering('ozgur', ref(edit), mocks.accept, page)
            return () => h('div')
          }
        })
      )
    )
    await state.open()
    await flushPromises()
    return state
  }
  it('submits only selected documents with document and cover page versions', async () => {
    const state = await setup()
    state.rows.value[1].selected = false
    await state.submit()
    expect(mocks.create).toHaveBeenCalledTimes(1)
    expect(mocks.create).toHaveBeenCalledWith(
      'ozgur',
      expect.any(String),
      expect.objectContaining({ version: 3, cover_page: expect.objectContaining({ version: 2 }) }),
      'first',
      'CP',
      {}
    )
    await state.submit()
    expect(mocks.create).toHaveBeenCalledTimes(1)
  })
  it('sends each selected document’s own ATA and MOC values', async () => {
    mocks.format.mockResolvedValue({
      fields: ['ata', 'moc'].map((key) => ({ key, required: true, default: null, max_length: 5 }))
    })
    const state = await setup()
    expect(state.canSubmit.value).toBe(false)
    Object.assign(state.rows.value[0].document, { ata: '27-00', moc: '0' })
    Object.assign(state.rows.value[1].document, { ata: '28-00', moc: '3' })
    expect(state.canSubmit.value).toBe(true)
    await state.submit()
    expect(mocks.create.mock.calls.map((call) => call[5])).toEqual([
      { ata: '2700', moc: '0' },
      { ata: '2800', moc: '3' }
    ])
  })
  it('continues after a failure and reuses the same identity and snapshot on retry', async () => {
    mocks.create.mockRejectedValueOnce(new Error('Connection lost')).mockResolvedValue(queued)
    const state = await setup()
    await state.submit()
    expect(mocks.create).toHaveBeenCalledTimes(2)
    expect(state.rows.value[0].error).toBeTruthy()
    const first = mocks.create.mock.calls[0]
    await state.submit()
    expect(mocks.create.mock.calls[2]).toEqual(first)
  })
  it('restores existing requests and resumes failed jobs without requesting new numbers', async () => {
    const failed = { ...queued, format_code: 'ORIGINAL', job: { status: 'failed' } }
    mocks.existing.mockResolvedValueOnce(failed).mockResolvedValueOnce(queued)
    mocks.resume.mockResolvedValue(queued)
    const state = await setup()
    await state.submit()
    expect(mocks.resume).toHaveBeenCalledExactlyOnceWith('ozgur', failed)
    expect(mocks.create).not.toHaveBeenCalled()
  })
  it('polls results, updates documents once and stops polling after close', async () => {
    const state = await setup()
    state.rows.value[1].selected = false
    await state.submit()
    mocks.fetch.mockResolvedValue({
      ...queued,
      status: 'completed',
      number: 'CP-1',
      document: { id: 'first' },
      job: { status: 'succeeded' }
    })
    await vi.advanceTimersByTimeAsync(2000)
    expect(state.completed.value).toBe(1)
    expect(mocks.accept).toHaveBeenCalledExactlyOnceWith({ id: 'first' })
    state.close()
    await vi.advanceTimersByTimeAsync(6000)
    expect(mocks.fetch).toHaveBeenCalledTimes(1)
  })
  it('requires a format and editor permission and handles unavailable configuration', async () => {
    mocks.options.mockResolvedValue({ available: true, formats: ['CP', 'ALT'] })
    const state = await setup()
    await state.submit()
    expect(mocks.create).not.toHaveBeenCalled()
    state.format.value = 'ALT'
    await flushPromises()
    expect(state.canSubmit.value).toBe(true)
    const viewer = await setup(false)
    viewer.format.value = 'CP'
    await viewer.submit()
    expect(mocks.create).not.toHaveBeenCalled()
    mocks.options.mockResolvedValue({ available: false, formats: [] })
    const unavailable = await setup()
    expect(unavailable.canSubmit.value).toBe(false)
  })
  it('stops dispatching remaining rows when the project component unmounts', async () => {
    let resolve!: (value: unknown) => void
    mocks.create.mockImplementationOnce(
      () =>
        new Promise((done) => {
          resolve = done
        })
    )
    const state = await setup()
    const pending = state.submit()
    await flushPromises()
    wrappers[0].unmount()
    resolve(queued)
    await pending
    expect(mocks.create).toHaveBeenCalledTimes(1)
    expect(mocks.accept).not.toHaveBeenCalled()
  })
  it('reports loading errors and allows loading again', async () => {
    mocks.options.mockRejectedValueOnce(new Error('Unavailable'))
    const state = await setup()
    expect(state.error.value).toBeTruthy()
    expect(state.canSubmit.value).toBe(false)
    await state.load()
    expect(state.rows.value).toHaveLength(2)
  })
  it('takes only the current page, excludes numbered/archived rows, and refreshes scope after paging', async () => {
    const state = await setup()
    page.value = [
      document('visible'),
      { ...document('numbered'), cover_page_no: 'CP-1' },
      { ...document('archived'), is_archived: true }
    ]
    await state.open()
    await flushPromises()
    expect(state.rows.value.map((row) => row.document.id)).toEqual(['visible'])
    await state.submit()
    state.close()
    page.value = [document('next-page')]
    await state.open()
    await flushPromises()
    expect(state.rows.value.map((row) => row.document.id)).toEqual(['next-page'])
  })
  it('requires format fields and freezes supplied values across partial retries', async () => {
    mocks.format.mockResolvedValue({
      code: 'CP',
      fields: [{ key: 'department', required: true, default: null, max_length: 10 }]
    })
    const state = await setup()
    expect(state.canSubmit.value).toBe(false)
    state.context.values.value.department = 'ENG'
    mocks.create.mockRejectedValueOnce(new Error('Lost response')).mockResolvedValue(queued)
    await state.submit()
    state.context.values.value.department = 'CHANGED'
    await state.submit()
    expect(mocks.create.mock.calls.every((call) => call[5].department === 'ENG')).toBe(true)
  })
})
