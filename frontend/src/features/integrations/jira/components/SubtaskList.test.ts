// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import { reactive } from 'vue'
import SubtaskList from './SubtaskList.vue'

const http = vi.hoisted(() => ({ get: vi.fn(), put: vi.fn() }))
const identity = vi.hoisted(() => ({
  getUser: { id: 1 },
  getPreferences: {},
  updatePreference: vi.fn()
}))
vi.mock('@/shared/api/http', () => ({ apiClient: http }))
vi.mock('@/features/session/stores/session', () => ({ useSessionStore: () => sessionIdentity }))
const sessionIdentity = reactive(identity)
enableAutoUnmount(afterEach)

function renderList() {
  return mount(SubtaskList, {
    global: {
      stubs: {
        'n-tabs': { template: '<div><slot /><slot name="suffix" /></div>' },
        'n-tab-pane': { props: ['tab'], template: '<section><slot name="tab" /></section>' },
        'n-input-width': {
          props: ['modelValue'],
          template:
            '<input :value="modelValue" @input="$emit(\'update:modelValue\', $event.target.value)" />'
        },
        'n-button': {
          props: ['disabled'],
          template: '<button :disabled="disabled"><slot /></button>'
        },
        'n-alert': { template: '<aside><slot /></aside>' },
        'n-h3': true
      }
    }
  })
}

describe('saved JIRA lists', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    sessionIdentity.getUser.id = 1
  })

  it('loads saved content from the JIRA resource', async () => {
    http.get.mockResolvedValue({
      data: { lists: [{ title: 'Saved review', list: [] }], version: 4 }
    })
    const wrapper = renderList()
    await flushPromises()
    expect(wrapper.text()).toContain('Saved review')
  })

  it('blocks saving after load failure and lets the owner retry', async () => {
    http.get.mockRejectedValueOnce(new Error('offline')).mockResolvedValueOnce({
      data: { lists: [{ title: 'Recovered list', list: [] }], version: 2 }
    })
    const wrapper = renderList()
    await flushPromises()
    expect(
      wrapper
        .findAll('button')
        .find((button) => button.text() === 'Save')!
        .attributes('disabled')
    ).toBeDefined()
    const retry = wrapper.findAll('button').find((button) => button.text() === 'Retry loading')
    expect(retry).toBeDefined()
    await retry!.trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('Recovered list')
  })

  it('clears an in-progress title edit before showing another account content', async () => {
    http.get
      .mockResolvedValueOnce({
        data: { lists: [{ title: 'Account A private title', list: [] }], version: 1 }
      })
      .mockResolvedValueOnce({
        data: { lists: [{ title: 'Account B list', list: [] }], version: 1 }
      })
    const wrapper = renderList()
    await flushPromises()
    await wrapper.get('section span').trigger('dblclick')
    await wrapper.get('input').setValue('Account A unsaved title')
    sessionIdentity.getUser.id = 2
    await flushPromises()
    expect(wrapper.text()).toContain('Account B list')
    expect(wrapper.find('input').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('Account A')
    wrapper.unmount()
  })
})
