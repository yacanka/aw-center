// @vitest-environment jsdom
import { mount } from '@vue/test-utils'
import { flushPromises } from '@vue/test-utils'
import { afterEach, expect, it, vi } from 'vitest'
import { NAlert, NButton, NCard, NFormItem, NInput, NSpace, NTable } from 'naive-ui'
import DeveloperTestData from './DeveloperTestData.vue'
import { previewTestDataReset, resetTestData } from '@/features/tools/api/developerTestData'

vi.mock('@/features/tools/api/developerTestData', () => ({
  previewTestDataReset: vi.fn(),
  resetTestData: vi.fn()
}))

afterEach(() => vi.resetAllMocks())

it('requires a preview and the exact phrase before resetting', async () => {
  const preview = {
    counts: { documents: 3 },
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
  expect(wrapper.findAll('button')[1].attributes('disabled')).toBeDefined()
  await wrapper.get('input').setValue('RESET')
  await wrapper.findAll('button')[1].trigger('click')
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
