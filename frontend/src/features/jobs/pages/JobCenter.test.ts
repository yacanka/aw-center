// @vitest-environment jsdom
import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  create,
  NAlert,
  NButton,
  NCard,
  NEmpty,
  NFlex,
  NH2,
  NList,
  NListItem,
  NPagination,
  NProgress,
  NSpace,
  NSwitch,
  NTag,
  NText,
  NThing
} from 'naive-ui'
import type { Job } from '../api/jobs'

vi.mock('vue-router', () => ({ useRoute: () => ({ query: {} }) }))
vi.mock('../api/jobs', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../api/jobs')>()),
  fetchJobs: vi.fn(),
  fetchJob: vi.fn(),
  fetchJobSystemStatus: vi.fn(),
  cancelJob: vi.fn()
}))
import * as api from '../api/jobs'
import JobCenter from './JobCenter.vue'
import JobListItem from '../components/JobListItem.vue'

const naive = create({
  components: [
    NAlert,
    NButton,
    NCard,
    NEmpty,
    NFlex,
    NH2,
    NList,
    NListItem,
    NPagination,
    NProgress,
    NSpace,
    NSwitch,
    NTag,
    NText,
    NThing
  ]
})
function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (error: Error) => void
  const promise = new Promise<T>((accept, fail) => {
    resolve = accept
    reject = fail
  })
  return { promise, resolve, reject }
}
function job(id: string): Job {
  return {
    id,
    kind: 'word.analyze',
    title: id,
    status: 'queued',
    progress: 0,
    message: '',
    error_code: '',
    input_name: '',
    output_name: '',
    result_summary: {},
    attempt: 0,
    max_attempts: 3,
    source_job: null,
    workflow_run: null,
    workflow_step: null,
    request_id: '',
    created_at: '2026-10-23T00:00:00Z',
    started_at: null,
    completed_at: null,
    confirmation_expires_at: null,
    updated_at: '2026-10-23T00:00:00Z',
    can_cancel: true,
    download_url: null,
    recovery_hint: '',
    jira_draft: null
  }
}
function page(id: string) {
  return { count: 40, next: null, previous: null, results: [job(id)] }
}
const wrappers: ReturnType<typeof mount>[] = []
function center() {
  const wrapper = mount(JobCenter, {
    global: { plugins: [naive], stubs: { JobDetailDrawer: true } }
  })
  wrappers.push(wrapper)
  return wrapper
}
beforeEach(() => {
  vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })
  vi.clearAllMocks()
  vi.mocked(api.fetchJobs).mockResolvedValue(page('current'))
  vi.mocked(api.fetchJobSystemStatus).mockResolvedValue({
    available: true,
    active_workers: 1,
    counts: {}
  })
  window.$message = { success: vi.fn(), error: vi.fn() } as unknown as typeof window.$message
})
afterEach(() => {
  wrappers.splice(0).forEach((wrapper) => wrapper.unmount())
  vi.useRealTimers()
})

describe('Job Center polling lifecycle', () => {
  it.each(['success', 'failure'] as const)(
    'does not restart polling after an in-flight %s completes following unmount',
    async (outcome) => {
      const pending = deferred<Awaited<ReturnType<typeof api.fetchJobs>>>()
      vi.mocked(api.fetchJobs).mockReturnValueOnce(pending.promise)
      const wrapper = center()
      wrapper.unmount()
      if (outcome === 'success') pending.resolve(page('old'))
      else pending.reject(new Error('Offline'))
      await flushPromises()
      await vi.advanceTimersByTimeAsync(9000)
      expect(api.fetchJobs).toHaveBeenCalledOnce()
      expect(api.fetchJobSystemStatus).toHaveBeenCalledOnce()
    }
  )

  it('keeps the selected page when a previous page poll finishes later', async () => {
    const wrapper = center()
    await flushPromises()
    const previousPage = deferred<Awaited<ReturnType<typeof api.fetchJobs>>>()
    const currentPage = deferred<Awaited<ReturnType<typeof api.fetchJobs>>>()
    vi.mocked(api.fetchJobs)
      .mockReturnValueOnce(previousPage.promise)
      .mockReturnValueOnce(currentPage.promise)
    await vi.advanceTimersByTimeAsync(3000)
    wrapper.findComponent(NPagination).vm.$emit('update:page', 2)
    await flushPromises()
    currentPage.resolve(page('page-two'))
    await flushPromises()
    previousPage.resolve(page('page-one'))
    await flushPromises()
    expect(wrapper.findComponent(JobListItem).props('job').id).toBe('page-two')
    expect(api.fetchJobs).toHaveBeenLastCalledWith(2, 20)
  })

  it('does not refresh or notify after a cancellation finishes on an unmounted page', async () => {
    const wrapper = center()
    await flushPromises()
    const cancellation = deferred<Job>()
    vi.mocked(api.cancelJob).mockReturnValueOnce(cancellation.promise)
    await wrapper
      .findAll('button')
      .find((button) => button.text() === 'Cancel')!
      .trigger('click')
    wrapper.unmount()
    cancellation.resolve({ ...job('current'), status: 'cancel_requested' })
    await flushPromises()
    await vi.advanceTimersByTimeAsync(3000)
    expect(api.fetchJobs).toHaveBeenCalledOnce()
    expect(window.$message.success).not.toHaveBeenCalled()
  })

  it('keeps the latest requested job details when an earlier detail response arrives later', async () => {
    vi.mocked(api.fetchJobs).mockResolvedValueOnce({ ...page('A'), results: [job('A'), job('B')] })
    const wrapper = center()
    await flushPromises()
    const previous = deferred<Job>()
    const current = deferred<Job>()
    vi.mocked(api.fetchJob)
      .mockReturnValueOnce(previous.promise)
      .mockReturnValueOnce(current.promise)
    const buttons = wrapper.findAll('button').filter((button) => button.text() === 'Details')
    await buttons[0].trigger('click')
    await buttons[1].trigger('click')
    current.resolve(job('B'))
    await flushPromises()
    previous.resolve(job('A'))
    await flushPromises()
    expect(wrapper.findComponent({ name: 'JobDetailDrawer' }).props('job').id).toBe('B')
  })
})
