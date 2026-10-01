// @vitest-environment jsdom
import { defineComponent } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, expect, it, vi } from 'vitest'
import type { Job } from '@/features/jobs/api/jobs'
const mocks = vi.hoisted(() => ({ fetch: vi.fn(), replace: vi.fn() }))
vi.mock('vue-router', () => ({
  useRoute: () => ({ query: { comparison_job: 'old-job' } }),
  useRouter: () => ({ replace: mocks.replace })
}))
vi.mock('@/features/jobs/api/jobs', () => ({
  fetchJob: mocks.fetch,
  isActiveJobStatus: () => false,
  cancelJob: vi.fn(),
  downloadJob: vi.fn()
}))
import { usePageJob } from './usePageJob'
beforeEach(() => vi.clearAllMocks())
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
