// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import Settings from './Settings.vue'
import { useSessionStore } from '@/features/session/stores/session'

vi.mock('vue-router', () => ({ useRouter: () => ({ push: vi.fn() }) }))
vi.mock('@/app/services/theme', () => ({ applyPreferredTheme: vi.fn() }))
import { applyPreferredTheme } from '@/app/services/theme'

function renderSettings() {
  return mount(Settings, {
    global: {
      stubs: {
        PasswordPopup: true,
        'n-switch': true,
        'n-select': true,
        'n-button': { template: '<button><slot /></button>' }
      }
    }
  })
}

describe('settings preferences', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    useSessionStore().user = {
      id: 1,
      username: 'test-user',
      first_name: 'Test',
      last_name: 'User',
      preferences: { theme: 'light' }
    }
  })

  it('shows account information and saves the system theme before applying it', async () => {
    const store = useSessionStore()
    const update = vi.spyOn(store, 'updatePreference').mockImplementation(async (preference) => {
      store.user!.preferences = preference
    })
    const wrapper = renderSettings()
    expect(wrapper.get('#account-heading').text()).toBe('Test User')
    await wrapper.get('input[value="system"]').setValue()
    await flushPromises()
    expect(update).toHaveBeenCalledWith({ theme: 'system' })
    expect(applyPreferredTheme).toHaveBeenCalledWith({ theme: 'system' })
    expect((wrapper.get('input[value="system"]').element as HTMLInputElement).checked).toBe(true)
  })

  it('retains the saved selection when the preference request fails', async () => {
    vi.spyOn(useSessionStore(), 'updatePreference').mockRejectedValue(new Error('offline'))
    const wrapper = renderSettings()
    await wrapper.get('input[value="dark"]').setValue()
    await flushPromises()
    expect(applyPreferredTheme).not.toHaveBeenCalled()
    expect((wrapper.get('input[value="light"]').element as HTMLInputElement).checked).toBe(true)
    expect(wrapper.get('fieldset').attributes('disabled')).toBeUndefined()
  })
})
