// @vitest-environment jsdom

import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { Job } from '@/features/jobs/api/jobs'

const api = vi.hoisted(() => ({
  fetchDoorsStatus: vi.fn(),
  enqueueDoorsModuleCheck: vi.fn(),
  enqueueDoorsObjectCreate: vi.fn(),
  enqueueDoorsObjectUpdate: vi.fn(),
  fetchDoorsDeveloperResult: vi.fn()
}))
const jobs = vi.hoisted(() => ({ fetchJob: vi.fn() }))
const routing = vi.hoisted(() => ({
  query: {} as Record<string, string>,
  replace: vi.fn(),
  push: vi.fn()
}))
vi.mock('@/features/integrations/api/doorsAutomation', () => api)
vi.mock('@/features/jobs/api/jobs', async (original) => ({
  ...(await original<object>()),
  ...jobs
}))
vi.mock('vue-router', () => ({ useRoute: () => routing, useRouter: () => routing }))

import DoorsDeveloper from './DoorsDeveloper.vue'

const slot = { template: '<div><slot /></div>' }
const stubs = {
  NSpace: slot,
  NForm: slot,
  NGrid: slot,
  NFormItemGi: slot,
  NText: slot,
  NFlex: slot,
  NTag: slot,
  NProgress: true,
  NCard: { props: ['title'], template: '<section><h2>{{ title }}</h2><slot /></section>' },
  NAlert: {
    props: ['title', 'type'],
    template: '<aside :data-type="type">{{ title }}<slot /></aside>'
  },
  NButton: { props: ['disabled'], template: '<button :disabled="disabled"><slot /></button>' },
  NCode: { props: ['code'], template: '<pre>{{ code }}</pre>' },
  NInput: {
    props: ['value'],
    emits: ['update:value'],
    template: '<input :value="value" @input="$emit(\'update:value\', $event.target.value)" />'
  },
  NInputNumber: { props: ['value'], template: '<input type="number" :value="value" />' },
  NSelect: true
}

describe('Developer DOORS operation results', () => {
  let wrapper: VueWrapper | undefined

  beforeEach(() => {
    vi.resetAllMocks()
    vi.useFakeTimers()
    routing.query = {}
    window.$message = { success: vi.fn(), error: vi.fn() } as never
    api.fetchDoorsStatus.mockResolvedValue({ available: true })
  })

  afterEach(() => {
    wrapper?.unmount()
    vi.useRealTimers()
  })

  async function open() {
    wrapper = mount(DoorsDeveloper, { global: { stubs } })
    await flushPromises()
    return wrapper
  }

  it.each([true, false])(
    'polls a queued check and shows its accessibility result: %s',
    async (accessible) => {
      api.enqueueDoorsModuleCheck.mockResolvedValue(job('queued'))
      jobs.fetchJob.mockResolvedValue(job('succeeded'))
      api.fetchDoorsDeveloperResult.mockResolvedValue(checkResult(accessible))
      const page = await open()
      await page.find('input').setValue('/Project/Module')
      await button(page, 'Queue module check').trigger('click')
      await flushPromises()
      expect(button(page, 'Queue module check').attributes('disabled')).toBeDefined()
      await vi.advanceTimersByTimeAsync(2000)
      await flushPromises()
      expect(jobs.fetchJob).toHaveBeenCalledWith('job-1')
      expect(page.text()).toContain(
        accessible ? 'Module found and readable' : 'Module not found or no read access'
      )
      expect(page.text()).toContain(accessible ? 'MODULE_OPENED' : 'OPEN_MODULE')
      expect(page.find(`aside[data-type="${accessible ? 'success' : 'warning'}"]`).exists()).toBe(
        true
      )
      expect(page.text()).not.toContain('operation failed')
      expect(routing.replace).toHaveBeenCalledWith({ query: { doors_developer_job: 'job-1' } })
    }
  )

  it('restores a completed result and uses the returned object as the next update input', async () => {
    routing.query = { doors_developer_job: 'job-1' }
    jobs.fetchJob.mockResolvedValue(job('succeeded', 'doors.create_object'))
    api.fetchDoorsDeveloperResult.mockResolvedValue({
      absolute_number: 42,
      identifier: 'REQ-42',
      operation_result: {
        schema_version: 1,
        operation: 'create_object',
        outcome: 'success',
        code: 'OBJECT_CREATED',
        message: 'Object created and saved.',
        input: { module_path: '/Project/Created' }
      }
    })
    api.enqueueDoorsObjectUpdate.mockResolvedValue(job('queued', 'doors.update_object'))
    const page = await open()
    expect(page.text()).toContain('Object: 42')
    await button(page, 'Use this object for the next operation').trigger('click')
    await button(page, 'Queue object update').trigger('click')
    await flushPromises()
    expect(api.enqueueDoorsObjectUpdate).toHaveBeenCalledWith(
      expect.objectContaining({
        module_path: '/Project/Created',
        absolute_number: 42
      }),
      expect.any(String)
    )
    expect(page.text()).not.toContain('OBJECT_CREATED')
  })

  it('shows execution failures without trying to download an operation result', async () => {
    routing.query = { doors_developer_job: 'job-1' }
    jobs.fetchJob.mockResolvedValue({
      ...job('failed'),
      error_code: 'DOORS_DXL_FAILED',
      message: 'DXL execution could not be completed.'
    })
    const page = await open()
    expect(page.text()).toContain('DOORS_DXL_FAILED')
    expect(api.fetchDoorsDeveloperResult).not.toHaveBeenCalled()
  })

  it('allows retrying a failed artifact read without rerunning the operation', async () => {
    routing.query = { doors_developer_job: 'job-1' }
    jobs.fetchJob.mockResolvedValue(job('succeeded'))
    api.fetchDoorsDeveloperResult
      .mockRejectedValueOnce(new Error('Result unavailable'))
      .mockResolvedValueOnce(checkResult(false))
    const page = await open()
    await button(page, 'Retry loading result').trigger('click')
    await flushPromises()
    expect(page.text()).toContain('OPEN_MODULE')
    expect(api.enqueueDoorsModuleCheck).not.toHaveBeenCalled()
  })
})

function button(page: VueWrapper, text: string) {
  const result = page.findAll('button').find((item) => item.text() === text)
  if (!result) throw new Error(`Missing button: ${text}`)
  return result
}

function job(status: Job['status'], kind = 'doors.run_dxl'): Job {
  return {
    id: 'job-1',
    title: 'DOORS operation',
    kind,
    status,
    progress: status === 'queued' ? 0 : 100,
    message: 'DOORS check completed.',
    error_code: '',
    recovery_hint: '',
    attempt: 1,
    max_attempts: 1,
    can_cancel: false,
    download_url: status === 'succeeded' ? '/api/jobs/job-1/download/' : null
  } as Job
}

function checkResult(accessible: boolean) {
  return {
    accessible,
    operation_result: {
      schema_version: 1,
      operation: 'check_module',
      outcome: accessible ? 'success' : 'negative',
      code: accessible ? 'MODULE_OPENED' : 'OPEN_MODULE',
      message: accessible ? 'Module found and readable.' : 'Module not found or no read access.',
      input: { module_path: '/Project/Module' }
    }
  }
}
