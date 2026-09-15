// @vitest-environment jsdom
import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { NButton, NCheckbox, NConfigProvider, NSelect } from 'naive-ui'
import { NAIVE_UI_COMPONENTS } from '@/app/plugins/naiveUi'
import { NAIVE_UI_FEATURE_COMPONENTS } from '@/app/plugins/naiveUiFeatures'
import { createEmptyCompdoc } from '../api/compdocCatalog'

const mocks = vi.hoisted(() => ({
  options: vi.fn(),
  format: vi.fn(),
  existing: vi.fn(),
  create: vi.fn()
}))
vi.mock('../api/compdocNumbering', () => ({
  fetchNumberingOptions: mocks.options,
  fetchNumberingFormat: mocks.format,
  fetchExistingCoverPageAllocation: mocks.existing,
  createCoverPageAllocation: mocks.create,
  fetchCoverPageAllocation: vi.fn(),
  resumeCoverPageAllocation: vi.fn()
}))
import CompDocBulkNumbering from './CompDocBulkNumbering.vue'

const Modal = {
  components: { NConfigProvider },
  props: ['show', 'preset', 'closable', 'maskClosable', 'closeOnEsc'],
  emits: ['update:show'],
  template:
    '<n-config-provider><section v-if="show"><slot /><slot name="footer" /></section></n-config-provider>'
}
const wrappers: ReturnType<typeof mount>[] = []
beforeEach(() => {
  vi.resetAllMocks()
  mocks.options.mockResolvedValue({ available: true, formats: ['CP', 'ALT'] })
  mocks.format.mockResolvedValue({ code: 'CP', fields: [] })
  mocks.existing.mockResolvedValue(null)
})
afterEach(() => wrappers.splice(0).forEach((wrapper) => wrapper.unmount()))

async function open(canEdit = true) {
  const wrapper = mount(CompDocBulkNumbering, {
    props: {
      project: 'ozgur',
      canEdit,
      documents: ['first', 'second'].map((id) => ({ ...createEmptyCompdoc(), id, name: id }))
    },
    global: {
      components: {
        ...Object.fromEntries(
          [...NAIVE_UI_COMPONENTS, ...NAIVE_UI_FEATURE_COMPONENTS].map((component) => [
            `N${component.name}`,
            component
          ])
        ),
        NModal: Modal
      }
    }
  })
  wrappers.push(wrapper)
  await wrapper.vm.open()
  await flushPromises()
  return wrapper
}

it('keeps Naive UI selection, format and submit controls connected', async () => {
  const wrapper = await open()
  expect(wrapper.findComponent(Modal).props('preset')).toBe('card')
  expect(wrapper.classes()).toContain('app-modal--large')
  const selection = () => wrapper.findAllComponents(NCheckbox)
  selection()[1].vm.$emit('update:checked', false)
  await flushPromises()
  expect(selection()[0].props('indeterminate')).toBe(true)
  expect(wrapper.text()).toContain('1 of 2 documents selected')
  selection()[0].vm.$emit('update:checked', true)
  wrapper.findComponent(NSelect).vm.$emit('update:value', 'ALT')
  await flushPromises()
  expect(wrapper.text()).toContain('2 of 2 documents selected')

  let complete!: (value: unknown) => void
  mocks.create.mockImplementationOnce(
    () =>
      new Promise((resolve) => {
        complete = resolve
      })
  )
  mocks.create.mockResolvedValue({ id: 'allocation', status: 'completed', number: 'CP-1' })
  await wrapper
    .findAllComponents(NButton)
    .find((button) => button.text() === 'Assign 2 numbers')!
    .trigger('click')
  await flushPromises()
  expect(wrapper.findComponent(Modal).props()).toMatchObject({
    closable: false,
    maskClosable: false,
    closeOnEsc: false
  })
  expect(selection().every((checkbox) => checkbox.props('disabled'))).toBe(true)
  expect(wrapper.findComponent(NSelect).props('disabled')).toBe(true)
  expect(mocks.create.mock.calls[0][4]).toBe('ALT')
  complete({ id: 'allocation-first', status: 'completed', number: 'CP-1' })
  await flushPromises()
  expect(mocks.create).toHaveBeenCalledTimes(2)
  expect(wrapper.text()).toContain('2 of 2 assigned')
  expect(wrapper.findComponent(Modal).props('closable')).toBe(true)
})

it('keeps selection and assignment disabled without edit permission', async () => {
  const wrapper = await open(false)
  expect(wrapper.findAllComponents(NCheckbox).every((checkbox) => checkbox.props('disabled'))).toBe(
    true
  )
  expect(
    wrapper
      .findAllComponents(NButton)
      .find((button) => button.text() === 'Assign 2 numbers')!
      .props('disabled')
  ).toBe(true)
})

it('shows a loading error and lets the user retry with the same modal', async () => {
  mocks.options.mockRejectedValueOnce(new Error('Unavailable'))
  const wrapper = await open()
  expect(wrapper.find('[role="alert"]').exists()).toBe(true)
  await wrapper
    .findAllComponents(NButton)
    .find((button) => button.text() === 'Retry loading')!
    .trigger('click')
  await flushPromises()
  expect(wrapper.find('[role="alert"]').exists()).toBe(false)
  expect(wrapper.text()).toContain('2 of 2 documents selected')
})
