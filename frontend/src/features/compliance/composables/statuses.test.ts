// @vitest-environment jsdom
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, h, ref } from 'vue'
import { beforeEach, expect, it, vi } from 'vitest'
import { useCompdocStatuses } from './statuses'

const fetch = vi.hoisted(() => vi.fn())
vi.mock('../api/compdocStatuses', () => ({ fetchCompdocStatuses: fetch }))
beforeEach(() => fetch.mockReset())

it('clears old vocabulary on project changes and ignores stale responses', async () => {
  const project = ref('ozgur')
  let resolveFirst!: (value: unknown) => void
  fetch.mockImplementationOnce(
    () =>
      new Promise((resolve) => {
        resolveFirst = resolve
      })
  )
  fetch.mockResolvedValueOnce([{ id: 'new', value: 'aesa_only', label: 'AESA only' }])
  let catalog!: ReturnType<typeof useCompdocStatuses>
  const wrapper = mount(
    defineComponent({
      setup() {
        catalog = useCompdocStatuses(() => project.value)
        return () => h('div', catalog.statuses.value.map((item) => item.label).join(','))
      }
    })
  )
  project.value = 'aesa'
  await flushPromises()
  expect(wrapper.text()).toBe('AESA only')
  resolveFirst([{ id: 'old', value: 'ozgur_only', label: 'Ozgur only' }])
  await flushPromises()
  expect(wrapper.text()).toBe('AESA only')
  expect(catalog.loading.value).toBe(false)
  wrapper.unmount()
})

it('clears failed options, exposes retry, and reloads when a panel reopens', async () => {
  const enabled = ref(true)
  fetch.mockRejectedValueOnce(new Error('Unavailable'))
  fetch.mockResolvedValue([{ id: 'status', value: 'review', label: 'Review' }])
  let catalog!: ReturnType<typeof useCompdocStatuses>
  const wrapper = mount(
    defineComponent({
      setup() {
        catalog = useCompdocStatuses(
          () => 'ozgur',
          () => enabled.value
        )
        return () => h('div')
      }
    })
  )
  await flushPromises()
  expect(catalog.error.value).not.toBe('')
  expect(catalog.statuses.value).toEqual([])
  await catalog.load()
  expect(catalog.error.value).toBe('')
  expect(catalog.statuses.value).toHaveLength(1)
  enabled.value = false
  await flushPromises()
  expect(catalog.statuses.value).toEqual([])
  enabled.value = true
  await flushPromises()
  expect(fetch).toHaveBeenCalledTimes(3)
  wrapper.unmount()
})
