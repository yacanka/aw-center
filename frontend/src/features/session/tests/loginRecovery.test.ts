// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import Login from '../pages/Login.vue'
import { naiveUi } from '@/app/plugins/naiveUi'
import { apiClient } from '@/shared/api/http'
import { captureInitialPasswordResetCapability } from '@/features/session/services/passwordResetCapability'

let wrapper: VueWrapper | undefined

async function renderReset() {
  captureInitialPasswordResetCapability(
    { pathname: '/app/login', search: '', hash: '#uid=MQ&token=synthetic-capability' },
    { state: null, replaceState: vi.fn() }
  )
  const router = createRouter({
    history: createMemoryHistory('/app/'),
    routes: [{ name: 'login', path: '/login', component: Login }]
  })
  await router.push('/login')
  wrapper = mount(Login, {
    global: {
      plugins: [router, naiveUi],
      stubs: { ParticleTextAnimator: true, LoginTagline: true }
    }
  })
  await wrapper.get('input[placeholder="Enter your new password"]').setValue('Synthetic-reset!42')
  await wrapper
    .get('input[placeholder="Enter your new password again"]')
    .setValue('Synthetic-reset!42')
  return wrapper
}

describe('password recovery completion', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.stubGlobal('$message', { success: vi.fn(), error: vi.fn() })
  })

  afterEach(() => {
    wrapper?.unmount()
    wrapper = undefined
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  it('shows normal login after a successful reset without a page refresh', async () => {
    const post = vi
      .spyOn(apiClient, 'post')
      .mockResolvedValue({ data: { detail: 'Password updated.' } })
    const page = await renderReset()
    expect(page.find('input[autocomplete="username"]').exists()).toBe(false)

    await page.get('button[type="submit"]').trigger('click')
    await flushPromises()

    expect(post).toHaveBeenCalledWith('users/password-reset/confirm/', {
      uid: 'MQ',
      token: 'synthetic-capability',
      new_password: 'Synthetic-reset!42'
    })
    expect(page.find('input[autocomplete="username"]').exists()).toBe(true)
    expect(page.find('input[placeholder="Enter your new password"]').exists()).toBe(false)
    expect(page.text()).toContain('Forgot Password?')
  })

  it('keeps the reset capability and input available after failure so a retry can finish', async () => {
    vi.spyOn(apiClient, 'post')
      .mockRejectedValueOnce(new Error('Connection unavailable'))
      .mockResolvedValueOnce({ data: { detail: 'Password updated.' } })
    const page = await renderReset()

    await page.get('button[type="submit"]').trigger('click')
    await flushPromises()
    expect(page.find('input[autocomplete="username"]').exists()).toBe(false)
    expect(
      (page.get('input[placeholder="Enter your new password"]').element as HTMLInputElement).value
    ).toBe('Synthetic-reset!42')

    await page.get('button[type="submit"]').trigger('click')
    await flushPromises()
    expect(page.find('input[autocomplete="username"]').exists()).toBe(true)
  })
})
