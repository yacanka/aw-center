// @vitest-environment jsdom
import { defineComponent } from 'vue'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import type { Job } from '@/features/jobs/api/jobs'
import type { DoorsModuleAttributesResult } from '@/features/integrations/api/doorsAutomation'

const api = vi.hoisted(() => ({
  enqueueDoorsModuleAttributes: vi.fn(),
  fetchDoorsModuleAttributesResult: vi.fn()
}))
const jobs = vi.hoisted(() => ({ fetchJob: vi.fn(), cancelJob: vi.fn(), downloadJob: vi.fn() }))
const routing = vi.hoisted(() => ({ query: {} as Record<string, string>, replace: vi.fn() }))
vi.mock('vue-router', () => ({ useRoute: () => routing, useRouter: () => routing }))
vi.mock('@/features/integrations/api/doorsAutomation', () => api)
vi.mock('@/features/jobs/api/jobs', async (original) => ({
  ...(await original<object>()),
  ...jobs
}))
import { useDoorsScriptAttributes } from './useDoorsScriptAttributes'

let state: ReturnType<typeof useDoorsScriptAttributes>
let wrapper: VueWrapper
beforeEach(() => {
  vi.resetAllMocks()
  routing.query = {}
  window.$message = { success: vi.fn(), error: vi.fn() } as never
})
afterEach(() => wrapper?.unmount())
function open() {
  wrapper = mount(
    defineComponent({
      setup() {
        state = useDoorsScriptAttributes()
        return () => null
      }
    })
  )
}
function completed(id: string): Job {
  return {
    id,
    kind: 'doors.run_dxl',
    status: 'succeeded',
    download_url: `/api/jobs/${id}/download/`
  } as Job
}
function result(path: string, name: string): DoorsModuleAttributesResult {
  return {
    type: 'doors_module_attributes',
    schema_version: 1,
    module_path: path,
    attributes: [name]
  }
}

it('a late result cannot overwrite a new module loaded after reset', async () => {
  routing.query = { doors_scripter_attributes_job: 'old' }
  jobs.fetchJob.mockResolvedValue(completed('old'))
  let resolveOld!: (value: DoorsModuleAttributesResult) => void
  api.fetchDoorsModuleAttributesResult.mockReturnValueOnce(
    new Promise((resolve) => {
      resolveOld = resolve
    })
  )
  open()
  await flushPromises()
  state.unload()
  state.modulePath.value = '/New'
  api.enqueueDoorsModuleAttributes.mockResolvedValue(completed('new'))
  api.fetchDoorsModuleAttributesResult.mockResolvedValue(result('/New', 'New Attribute'))
  await state.load()
  await flushPromises()
  resolveOld(result('/Old', 'Old Attribute'))
  await flushPromises()
  expect(state.names.value).toEqual(['New Attribute'])
  expect(state.modulePath.value).toBe('/New')
  expect(state.loading.value).toBe(false)
})

it('a late queue response after unmount does not change job state', async () => {
  let resolveQueue!: (value: Job) => void
  api.enqueueDoorsModuleAttributes.mockReturnValue(
    new Promise((resolve) => {
      resolveQueue = resolve
    })
  )
  open()
  state.modulePath.value = '/P/M'
  const request = state.load()
  wrapper.unmount()
  resolveQueue(completed('old'))
  await request
  expect(state.monitor.job.value).toBeNull()
  expect(state.names.value).toEqual([])
})

it('an uncertain retry reuses its idempotency key for the same module', async () => {
  api.enqueueDoorsModuleAttributes.mockRejectedValue(new Error('Network unavailable'))
  open()
  state.modulePath.value = '/P/M'
  await state.load()
  await state.load()
  expect(api.enqueueDoorsModuleAttributes.mock.calls[0][1]).toBe(
    api.enqueueDoorsModuleAttributes.mock.calls[1][1]
  )
  state.modulePath.value = '/Other'
  await state.load()
  expect(api.enqueueDoorsModuleAttributes.mock.calls[2][1]).not.toBe(
    api.enqueueDoorsModuleAttributes.mock.calls[0][1]
  )
})

it('an old download failure cannot detach a newer load', async () => {
  open()
  state.monitor.setJob(completed('old'))
  api.fetchDoorsModuleAttributesResult.mockResolvedValue(result('/Old', 'Old'))
  await flushPromises()
  let rejectDownload!: (error: Error) => void
  jobs.downloadJob.mockReturnValue(
    new Promise((_, reject) => {
      rejectDownload = reject
    })
  )
  const download = state.monitor.download()
  state.unload()
  state.modulePath.value = '/New'
  api.enqueueDoorsModuleAttributes.mockResolvedValue({ ...completed('new'), status: 'queued' })
  await state.load()
  rejectDownload(new Error('Old download failed'))
  await download
  await flushPromises()
  expect(state.monitor.job.value?.id).toBe('new')
  expect(state.error.value).toBe('')
  expect(state.loading.value).toBe(true)
})

it('an old cancellation response cannot replace the newer job', async () => {
  open()
  state.monitor.setJob({ ...completed('old'), status: 'running' })
  let resolveCancel!: (job: Job) => void
  jobs.cancelJob.mockReturnValue(
    new Promise((resolve) => {
      resolveCancel = resolve
    })
  )
  const cancellation = state.monitor.cancel()
  // The old job can finish while the cancellation request is still in flight.
  api.fetchDoorsModuleAttributesResult.mockResolvedValue(result('/Old', 'Old'))
  state.monitor.setJob(completed('old'))
  await flushPromises()
  state.unload()
  state.modulePath.value = '/New'
  api.enqueueDoorsModuleAttributes.mockResolvedValue({ ...completed('new'), status: 'queued' })
  await state.load()
  resolveCancel({ ...completed('old'), status: 'cancelled' })
  await cancellation
  await flushPromises()
  expect(state.monitor.job.value?.id).toBe('new')
  expect(state.names.value).toEqual([])
  expect(state.error.value).toBe('')
})
