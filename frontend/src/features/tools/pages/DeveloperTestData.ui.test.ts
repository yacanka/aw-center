// @vitest-environment jsdom
import { mount } from '@vue/test-utils'
import { flushPromises } from '@vue/test-utils'
import { afterEach, expect, it, vi } from 'vitest'
import { NAlert, NButton, NCard, NFormItem, NInput, NSpace, NTable } from 'naive-ui'
import DeveloperTestData from './DeveloperTestData.vue'
import {
  previewTestDataReset,
  resetTestData,
  prepareTestDataReset,
  releaseTestDataReset
} from '@/features/tools/api/developerTestData'

vi.mock('@/features/tools/api/developerTestData', () => ({
  previewTestDataReset: vi.fn(),
  resetTestData: vi.fn(),
  prepareTestDataReset: vi.fn(),
  releaseTestDataReset: vi.fn()
}))

afterEach(() => vi.resetAllMocks())

it('requires a preview and the exact phrase before resetting', async () => {
  const preview = {
    counts: { documents: 3 },
    prepared: true,
    ready: true,
    blockers: emptyBlockers(),
    confirmation_phrase: 'RESET',
    confirmation_token: 'signed'
  }
  vi.mocked(previewTestDataReset).mockResolvedValue(preview)
  vi.mocked(resetTestData).mockResolvedValue(undefined)
  const wrapper = mount(DeveloperTestData, {
    global: { components: { NAlert, NButton, NCard, NFormItem, NInput, NSpace, NTable } }
  })
  await wrapper.get('button').trigger('click')
  await flushPromises()
  expect(wrapper.text()).toContain('documents')
  expect(wrapper.findAll('button').at(-1)!.attributes('disabled')).toBeDefined()
  await wrapper.get('input').setValue('RESET')
  await wrapper.findAll('button').at(-1)!.trigger('click')
  await flushPromises()
  expect(resetTestData).toHaveBeenCalledWith(preview, 'RESET')
  expect(wrapper.text()).toContain('Test data was reset.')
  expect(wrapper.find('input').exists()).toBe(false)
  wrapper.unmount()
})

it('shows backend errors without enabling a reset', async () => {
  vi.mocked(previewTestDataReset).mockRejectedValue(
    new Error('Only a superuser can reset test data.')
  )
  const wrapper = mount(DeveloperTestData, {
    global: { components: { NAlert, NButton, NCard, NFormItem, NInput, NSpace, NTable } }
  })
  await wrapper.get('button').trigger('click')
  await flushPromises()
  expect(wrapper.text()).toContain('Only a superuser')
  expect(wrapper.find('input').exists()).toBe(false)
  expect(resetTestData).not.toHaveBeenCalled()
  wrapper.unmount()
})

function emptyBlockers() {
  return {
    jobs: [],
    job_count: 0,
    uncertain_jobs: [],
    uncertain_job_count: 0,
    allocations: [],
    allocation_count: 0,
    notification_count: 0
  }
}

it('prepares, shows blockers, and releases without deleting data', async () => {
  const preview = {
    counts: { documents: 3 },
    prepared: false,
    ready: false,
    blockers: emptyBlockers(),
    confirmation_phrase: 'RESET',
    confirmation_token: 'first'
  }
  const prepared = {
    ...preview,
    prepared: true,
    confirmation_token: 'prepared',
    blockers: {
      ...emptyBlockers(),
      job_count: 1,
      jobs: [
        { id: 'job-id', kind: 'compliance.allocate_cover_page_number', status: 'cancel_requested' }
      ]
    }
  }
  vi.mocked(previewTestDataReset).mockResolvedValue(preview)
  vi.mocked(prepareTestDataReset).mockResolvedValue(prepared)
  vi.mocked(releaseTestDataReset).mockResolvedValue(preview)
  const wrapper = mount(DeveloperTestData, {
    global: { components: { NAlert, NButton, NCard, NFormItem, NInput, NSpace, NTable } }
  })
  const button = (text: string) => wrapper.findAll('button').find((item) => item.text() === text)!
  await button('Preview reset').trigger('click')
  await flushPromises()
  await wrapper.get('input').setValue('RESET')
  expect(button('Reset compliance documents and organization').attributes('disabled')).toBeDefined()
  await button('Prepare and cancel related jobs').trigger('click')
  await flushPromises()
  expect(prepareTestDataReset).toHaveBeenCalledWith(preview)
  expect(wrapper.text()).toContain('job-id — cancel_requested')
  expect(button('Reset compliance documents and organization').attributes('disabled')).toBeDefined()
  await button('Release preparation').trigger('click')
  await flushPromises()
  expect(releaseTestDataReset).toHaveBeenCalledWith(prepared)
  expect(resetTestData).not.toHaveBeenCalled()
  wrapper.unmount()
})
