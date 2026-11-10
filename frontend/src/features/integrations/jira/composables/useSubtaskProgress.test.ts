// @vitest-environment jsdom
import { mount } from '@vue/test-utils'
import { computed, defineComponent, h, nextTick, ref } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { Job } from '@/features/jobs/api/jobs'

const mocks = vi.hoisted(() => ({ monitor: vi.fn(), post: vi.fn() }))
vi.mock('@/features/jobs/composables/usePageJob', () => ({ usePageJob: mocks.monitor }))
vi.mock('@/shared/api/http', () => ({ apiClient: { post: mocks.post } }))
import { createManualSubtaskJob, createWorkbookSubtaskJob } from '../api/jiraSubtasks'

import { useSubtaskProgress } from './useSubtaskProgress'

describe('original progress UI on durable subtask jobs', () => {
  const job = ref<Job | null>(null)
  const errorMessage = ref('')
  const notification = { success: vi.fn(), warning: vi.fn(), error: vi.fn() }
  const dialog = { warning: vi.fn() }
  const wrappers: ReturnType<typeof mount>[] = []

  beforeEach(() => {
    vi.resetAllMocks()
    job.value = null
    errorMessage.value = ''
    window.$notification = notification as unknown as typeof window.$notification
    window.$dialog = dialog as unknown as typeof window.$dialog
    mocks.monitor.mockReturnValue({
      job,
      errorMessage,
      active: computed(() =>
        ['queued', 'running', 'cancel_requested'].includes(job.value?.status || '')
      ),
      setJob: (value: Job) => {
        job.value = value
      }
    })
  })

  afterEach(() => wrappers.splice(0).forEach((wrapper) => wrapper.unmount()))

  function progress(queryKey: 'subtask_job' | 'excel_subtask_job' = 'subtask_job') {
    let result!: ReturnType<typeof useSubtaskProgress>
    wrappers.push(
      mount(
        defineComponent({
          setup() {
            result = useSubtaskProgress(queryKey)
            return () => h('div')
          }
        })
      )
    )
    return result
  }

  it.each(['subtask_job', 'excel_subtask_job'] as const)(
    'polls %s through completion without duplicate submits',
    async (key) => {
      const state = progress(key)
      const create = vi.fn().mockResolvedValue(batchJob('queued'))
      await state.submit(create, 'same-payload')
      await nextTick()
      expect(mocks.monitor).toHaveBeenCalledWith(key)
      expect(state.busy.value).toBe(true)
      expect(state.loadingBar.value.status).toBe('default')
      await state.submit(create, 'same-payload')
      expect(create).toHaveBeenCalledTimes(1)
      job.value = batchJob('running', 45)
      await nextTick()
      expect(state.loadingBar.value.percentage).toBe(45)
      job.value = batchJob('succeeded', 100)
      await nextTick()
      expect(state.loadingBar.value).toEqual({
        show: true,
        status: 'success',
        percentage: 100,
        content: ''
      })
      expect(state.busy.value).toBe(false)
      expect(notification.success).toHaveBeenCalledTimes(1)
    }
  )

  it.each(['manual', 'workbook'] as const)(
    'replays %s after a lost enqueue response using the same key',
    async (kind) => {
      const state = progress(kind === 'manual' ? 'subtask_job' : 'excel_subtask_job')
      const file = new File(['workbook'], 'tasks.xlsx')
      const create = (key: string) =>
        kind === 'manual'
          ? createManualSubtaskJob('CHN-42', [{ summary: 'Review', fields: {} }], key)
          : createWorkbookSubtaskJob('CHN-42', file, [{ column: 'Title', field: 'summary' }], key)
      mocks.post
        .mockRejectedValueOnce(new Error('Response lost'))
        .mockResolvedValue({ data: batchJob('queued') })

      await state.submit(create, 'unchanged-plan', file)
      await state.submit(create, 'unchanged-plan', file)

      const [first, replay] = mocks.post.mock.calls
      expect(first[2].headers['Idempotency-Key']).toEqual(expect.any(String))
      expect(replay[2].headers['Idempotency-Key']).toBe(first[2].headers['Idempotency-Key'])
      expect(job.value?.id).toBe('subtask-job')
      job.value = batchJob('succeeded')
      await state.submit(create, 'unchanged-plan', file)
      expect(mocks.post.mock.calls[2][2].headers['Idempotency-Key']).not.toBe(
        first[2].headers['Idempotency-Key']
      )
    }
  )

  it('uses new keys for changed payloads and replacement files even when file metadata matches', async () => {
    const state = progress('excel_subtask_job')
    const keys: string[] = []
    const create = async (key: string) => {
      keys.push(key)
      throw new Error('Response lost')
    }
    const file = new File(['first'], 'tasks.xlsx', { lastModified: 1 })
    await state.submit(create, 'plan-A', file)
    await state.submit(create, 'plan-B', file)
    await state.submit(create, 'plan-B', new File(['other'], 'tasks.xlsx', { lastModified: 1 }))
    expect(keys.every((key) => typeof key === 'string' && key.length > 0)).toBe(true)
    expect(new Set(keys).size).toBe(3)
  })

  it('replays an unacknowledged resume and starts a fresh new batch after acknowledgement', async () => {
    const state = progress()
    job.value = batchJob('reconciliation_required')
    const create = vi.fn().mockResolvedValue(batchJob('queued'))
    mocks.post
      .mockRejectedValueOnce(new Error('Response lost'))
      .mockResolvedValue({ data: batchJob('queued') })
    await state.submit(create, 'edited-plan')
    await dialog.warning.mock.calls.at(-1)![0].onPositiveClick()
    await state.submit(create, 'edited-plan')
    await dialog.warning.mock.calls.at(-1)![0].onPositiveClick()
    expect(mocks.post.mock.calls[0][2].headers['Idempotency-Key']).toEqual(expect.any(String))
    expect(mocks.post.mock.calls[1][2].headers['Idempotency-Key']).toBe(
      mocks.post.mock.calls[0][2].headers['Idempotency-Key']
    )
    job.value = batchJob('failed')
    await state.submit(create, 'edited-plan')
    await dialog.warning.mock.calls.at(-1)![0].onNegativeClick()
    expect(create.mock.calls[0][0]).not.toBe(mocks.post.mock.calls[0][2].headers['Idempotency-Key'])
  })

  it('reports enqueue and polling errors without leaving a pending progress bar', async () => {
    const state = progress()
    await state.submit(
      vi.fn().mockRejectedValue(new Error('Could not queue subtasks.')),
      'same-payload'
    )
    expect(state.loadingBar.value.status).toBe('error')
    expect(state.busy.value).toBe(false)
    errorMessage.value = 'Could not load the job.'
    await nextTick()
    expect(state.loadingBar.value.content).toBe('Could not load the job.')
    expect(notification.error).toHaveBeenCalledTimes(2)
  })

  it('requires an explicit choice and resumes the immutable previous batch', async () => {
    const state = progress()
    job.value = batchJob('reconciliation_required', 45)
    await nextTick()
    const create = vi.fn()
    await state.submit(create, 'same-payload')
    expect(create).not.toHaveBeenCalled()
    expect(mocks.post).not.toHaveBeenCalled()
    const options = dialog.warning.mock.calls[0][0]
    expect(options.content).toContain('not your current edits')
    mocks.post.mockResolvedValue({ data: batchJob('queued') })
    await options.onPositiveClick()
    expect(mocks.post).toHaveBeenCalledWith(
      'integrations/jira/subtasks/jobs/subtask-job/resume/',
      {},
      { headers: { 'Idempotency-Key': expect.any(String) } }
    )
    expect(create).not.toHaveBeenCalled()
    expect(state.busy.value).toBe(true)
  })

  it('uses the edited form only when a new batch is explicitly selected', async () => {
    const state = progress()
    job.value = batchJob('failed', 10)
    await nextTick()
    const create = vi.fn().mockResolvedValue(batchJob('queued'))
    await state.submit(create, 'same-payload')
    const options = dialog.warning.mock.calls[0][0]
    expect(options.negativeText).toBe('Create new batch')
    await options.onNegativeClick()
    expect(create).toHaveBeenCalledOnce()
    expect(mocks.post).not.toHaveBeenCalled()
  })
})

function batchJob(status: Job['status'], progress = 0): Job {
  return {
    id: 'subtask-job',
    kind: 'dcc.create_jira_subtasks',
    status,
    progress,
    message: status === 'succeeded' ? 'Subtasks created successfully.' : 'Preparing subtasks.'
  } as Job
}
