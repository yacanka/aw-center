// @vitest-environment jsdom
import { defineComponent } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, expect, it, vi } from 'vitest'
import type { Job } from '@/features/jobs/api/jobs'
const mocks = vi.hoisted(() => ({
  fetch: vi.fn(),
  replace: vi.fn(),
  cancel: vi.fn(),
  download: vi.fn(),
  success: vi.fn()
}))
vi.mock('vue-router', () => ({
  useRoute: () => ({ query: { comparison_job: 'old-job' } }),
  useRouter: () => ({ replace: mocks.replace })
}))
vi.mock('@/features/jobs/api/jobs', () => ({
  fetchJob: mocks.fetch,
  isActiveJobStatus: () => false,
  cancelJob: mocks.cancel,
  downloadJob: mocks.download
}))
import { usePageJob } from './usePageJob'
beforeEach(() => {
  vi.resetAllMocks()
  mocks.fetch.mockReturnValue(new Promise(() => {}))
  window.$message = { success: mocks.success } as unknown as typeof window.$message
})
it('reset invalidates a pending restoration of the old file pair', async () => {
  let complete!: (job: Job) => void
  mocks.fetch.mockReturnValue(
    new Promise((resolve) => {
      complete = resolve
    })
  )
  let monitor!: ReturnType<typeof usePageJob>
  const wrapper = mount(
    defineComponent({
      setup() {
        monitor = usePageJob('comparison_job')
        return () => null
      }
    })
  )
  monitor.reset()
  complete({ id: 'old-job', status: 'succeeded' } as Job)
  await flushPromises()
  expect(monitor.job.value).toBeNull()
  expect(mocks.replace).toHaveBeenCalledWith({ query: {} })
  wrapper.unmount()
})
it('a newly submitted job cannot be replaced by an earlier refresh', async () => {
  let complete!: (job: Job) => void
  mocks.fetch.mockReturnValue(
    new Promise((resolve) => {
      complete = resolve
    })
  )
  let monitor!: ReturnType<typeof usePageJob>
  const wrapper = mount(
    defineComponent({
      setup() {
        monitor = usePageJob('comparison_job')
        return () => null
      }
    })
  )
  monitor.setJob({ id: 'new-job', status: 'queued' } as Job)
  complete({ id: 'old-job', status: 'succeeded' } as Job)
  await flushPromises()
  expect(monitor.job.value?.id).toBe('new-job')
  wrapper.unmount()
})

function setupMonitor() {
  let monitor!: ReturnType<typeof usePageJob>
  const wrapper = mount(
    defineComponent({
      setup() {
        monitor = usePageJob('comparison_job')
        return () => null
      }
    })
  )
  monitor.setJob({ id: 'old-job', status: 'running' } as Job)
  return { monitor, wrapper }
}

it('ignores an old cancellation after another job is selected', async () => {
  let complete!: (job: Job) => void
  mocks.cancel.mockReturnValue(
    new Promise((resolve) => {
      complete = resolve
    })
  )
  const { monitor, wrapper } = setupMonitor()
  const pending = monitor.cancel()
  monitor.setJob({ id: 'new-job', status: 'queued' } as Job)
  complete({ id: 'old-job', status: 'cancelled' } as Job)
  await pending
  expect(monitor.job.value?.id).toBe('new-job')
  expect(monitor.cancelling.value).toBe(false)
  expect(mocks.replace).toHaveBeenLastCalledWith({ query: { comparison_job: 'new-job' } })
  expect(mocks.success).not.toHaveBeenCalled()
  wrapper.unmount()
})

it('reset releases pending actions and rejects their late errors', async () => {
  let reject!: (error: Error) => void
  mocks.cancel.mockReturnValue(
    new Promise((_resolve, fail) => {
      reject = fail
    })
  )
  const { monitor, wrapper } = setupMonitor()
  const pending = monitor.cancel()
  monitor.reset()
  expect(monitor.cancelling.value).toBe(false)
  reject(new Error('old cancellation failed'))
  await pending
  expect(monitor.job.value).toBeNull()
  expect(monitor.errorMessage.value).toBe('')
  wrapper.unmount()
})

it('does not show cancellation success after unmount', async () => {
  let complete!: (job: Job) => void
  mocks.cancel.mockReturnValue(
    new Promise((resolve) => {
      complete = resolve
    })
  )
  const { monitor, wrapper } = setupMonitor()
  const pending = monitor.cancel()
  wrapper.unmount()
  complete({ id: 'old-job', status: 'cancelled' } as Job)
  await pending
  expect(mocks.success).not.toHaveBeenCalled()
})

it('applies current cancellation and prevents duplicate submits', async () => {
  let complete!: (job: Job) => void
  mocks.cancel.mockReturnValue(
    new Promise((resolve) => {
      complete = resolve
    })
  )
  const { monitor, wrapper } = setupMonitor()
  const pending = monitor.cancel()
  void monitor.cancel()
  expect(mocks.cancel).toHaveBeenCalledTimes(1)
  complete({ id: 'old-job', status: 'cancelled' } as Job)
  await pending
  expect(monitor.job.value?.status).toBe('cancelled')
  expect(monitor.cancelling.value).toBe(false)
  wrapper.unmount()
})

it('does not attach a previous download failure to a new job', async () => {
  let reject!: (error: Error) => void
  mocks.download.mockReturnValue(
    new Promise((_resolve, fail) => {
      reject = fail
    })
  )
  const { monitor, wrapper } = setupMonitor()
  const pending = monitor.download()
  monitor.setJob({ id: 'new-job', status: 'queued' } as Job)
  expect(monitor.downloading.value).toBe(false)
  reject(new Error('old download failed'))
  await pending
  expect(monitor.errorMessage.value).toBe('')
  wrapper.unmount()
})
