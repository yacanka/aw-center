// @vitest-environment jsdom
import { mount } from '@vue/test-utils'
import { computed, defineComponent, h, nextTick, ref } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { Job } from '@/features/jobs/api/jobs'

const mocks = vi.hoisted(() => ({ monitor: vi.fn(), resume: vi.fn() }))
vi.mock('@/features/jobs/composables/usePageJob', () => ({ usePageJob: mocks.monitor }))
vi.mock('@/features/dcc/api/jiraSubtasks', () => ({ resumeSubtaskJob: mocks.resume }))

import { useSubtaskProgress } from './useSubtaskProgress'

describe('original progress UI on durable subtask jobs', () => {
  const job = ref<Job | null>(null)
  const errorMessage = ref('')
  const notification = { success: vi.fn(), warning: vi.fn(), error: vi.fn() }
  const dialog = { warning: vi.fn() }
  const wrappers: ReturnType<typeof mount>[] = []

  beforeEach(() => {
    vi.clearAllMocks()
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
      await state.submit(create)
      await nextTick()
      expect(mocks.monitor).toHaveBeenCalledWith(key)
      expect(state.busy.value).toBe(true)
      expect(state.loadingBar.value.status).toBe('default')
      await state.submit(create)
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

  it('reports enqueue and polling errors without leaving a pending progress bar', async () => {
    const state = progress()
    await state.submit(vi.fn().mockRejectedValue(new Error('Could not queue subtasks.')))
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
    await state.submit(create)
    expect(create).not.toHaveBeenCalled()
    expect(mocks.resume).not.toHaveBeenCalled()
    const options = dialog.warning.mock.calls[0][0]
    expect(options.content).toContain('not your current edits')
    mocks.resume.mockResolvedValue(batchJob('queued'))
    await options.onPositiveClick()
    expect(mocks.resume).toHaveBeenCalledWith('subtask-job')
    expect(create).not.toHaveBeenCalled()
    expect(state.busy.value).toBe(true)
  })

  it('uses the edited form only when a new batch is explicitly selected', async () => {
    const state = progress()
    job.value = batchJob('failed', 10)
    await nextTick()
    const create = vi.fn().mockResolvedValue(batchJob('queued'))
    await state.submit(create)
    const options = dialog.warning.mock.calls[0][0]
    expect(options.negativeText).toBe('Create new batch')
    await options.onNegativeClick()
    expect(create).toHaveBeenCalledOnce()
    expect(mocks.resume).not.toHaveBeenCalled()
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
