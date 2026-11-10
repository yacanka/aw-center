// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { NButton, NForm, NFormItem, NInput } from 'naive-ui'
import Settings from '../pages/Settings.vue'
import { useSessionStore } from '@/features/session/stores/session'
import { apiClient } from '@/shared/api/http'

vi.mock('vue-router', () => ({ useRouter: () => ({ push: vi.fn() }) }))
vi.mock('@/shared/services/notify', () => ({ notifyError: vi.fn(), notifySuccess: vi.fn() }))

function renderSettings() {
  return mount(Settings, {
    global: {
      components: { NButton, NForm, NFormItem, NInput },
      stubs: { PasswordPopup: true, 'n-switch': true, 'n-select': true }
    }
  })
}

describe('self-service profile settings', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    setActivePinia(createPinia())
    useSessionStore().setAuthenticatedUser({
      id: 1,
      username: 'U12345',
      first_name: 'Before',
      last_name: 'User',
      email: 'before@example.com',
      permissions: [],
      preferences: { theme: 'dark' }
    })
  })

  it('saves identity fields and immediately refreshes account details while preserving preferences', async () => {
    const patch = vi.spyOn(apiClient, 'patch').mockResolvedValue({
      data: { first_name: 'Ada', last_name: 'Lovelace', email: 'ada@example.com' }
    })
    const wrapper = renderSettings()
    await wrapper.get('input[autocomplete="given-name"]').setValue('Ada')
    await wrapper.get('input[autocomplete="family-name"]').setValue('Lovelace')
    await wrapper.get('input[autocomplete="email"]').setValue('ada@example.com')
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(patch).toHaveBeenCalledWith('users/profile/', {
      first_name: 'Ada',
      last_name: 'Lovelace',
      email: 'ada@example.com'
    })
    expect(wrapper.get('#account-heading').text()).toBe('Ada Lovelace')
    expect(wrapper.get('.account-details').text()).toContain('ada@example.com')
    expect(useSessionStore().getPreferences.theme).toBe('dark')
    expect(useSessionStore().getUser.username).toBe('U12345')
    wrapper.unmount()
  })

  it('retains edits and saved identity when saving fails, and permits retry', async () => {
    vi.spyOn(apiClient, 'patch').mockRejectedValue(new Error('Connection unavailable'))
    const wrapper = renderSettings()
    await wrapper.get('input[autocomplete="given-name"]').setValue('Draft')
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(wrapper.get('#account-heading').text()).toBe('Before User')
    expect(
      (wrapper.get('input[autocomplete="given-name"]').element as HTMLInputElement).value
    ).toBe('Draft')
    expect(wrapper.get('[role="alert"]').text()).toContain('Connection unavailable')
    expect(wrapper.get('button[type="submit"]').attributes('disabled')).toBeUndefined()
    wrapper.unmount()
  })

  it('validates the email before sending the request', async () => {
    const patch = vi.spyOn(apiClient, 'patch')
    const wrapper = renderSettings()
    await wrapper.get('input[autocomplete="email"]').setValue('invalid')
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(patch).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('Enter a valid email address')
    wrapper.unmount()
  })
})
