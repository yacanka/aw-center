// @vitest-environment jsdom

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { createApp, defineComponent, nextTick } from 'vue'
import { mount } from '@vue/test-utils'

vi.mock('@/features/session/api/sessionApi', () => ({
  changeSessionPassword: vi.fn(),
  confirmPasswordReset: vi.fn(),
  createSession: vi.fn(),
  deleteSession: vi.fn(),
  fetchSession: vi.fn(),
  requestPasswordReset: vi.fn(),
  updateSessionPreferences: vi.fn()
}))
vi.mock('@/shared/services/notify', () => ({
  notifyError: vi.fn(),
  notifySuccess: vi.fn()
}))

import * as sessionApi from '@/features/session/api/sessionApi'
import { notifySuccess } from '@/shared/services/notify'
import { useSessionStore } from '@/features/session/stores/session'
import { useDccStore } from '@/features/dcc/stores/dcc'
import { registerSessionScopedStore } from '@/features/session/stores/sessionScope'

const currentUser = { id: 7, username: 'operator', is_active: true }
const SessionHarness = defineComponent({
  setup: () => ({ session: useSessionStore() }),
  template: '<output data-status>{{ session.status }}</output>'
})

describe('session store', () => {
  beforeEach(() => {
    const pinia = createPinia()
    pinia.use(registerSessionScopedStore)
    createApp({}).use(pinia)
    setActivePinia(pinia)
    vi.clearAllMocks()
  })

  it('authenticates only after the server session bootstrap succeeds', async () => {
    vi.mocked(sessionApi.fetchSession).mockResolvedValue({
      state: 'authenticated',
      user: currentUser
    })
    const session = useSessionStore()

    await expect(session.bootstrap()).resolves.toBe('authenticated')

    expect(session.getUser).toEqual(currentUser)
    expect(session.isAuthenticated).toBe(true)
    await session.bootstrap()
    expect(sessionApi.fetchSession).toHaveBeenCalledOnce()
  })

  it('treats the explicit anonymous bootstrap response as initialized and signed out', async () => {
    vi.mocked(sessionApi.fetchSession).mockResolvedValue({ state: 'anonymous', user: null })
    const session = useSessionStore()

    await expect(session.bootstrap()).resolves.toBe('anonymous')

    expect(session.isSessionInitialized).toBe(true)
    expect(session.isAuthenticated).toBe(false)
    expect(session.user).toBeNull()
  })

  it('fails closed on a network error and never restores a cached identity', async () => {
    vi.mocked(sessionApi.fetchSession).mockRejectedValue(new Error('offline'))
    const session = useSessionStore()

    await expect(session.bootstrap()).resolves.toBe('unavailable')

    expect(session.user).toBeNull()
    expect(session.isAuthenticated).toBe(false)
  })

  it('renders an unavailable session state after bootstrap transport failure', async () => {
    vi.mocked(sessionApi.fetchSession).mockRejectedValue(new Error('offline'))
    const wrapper = mount(SessionHarness)

    await wrapper.vm.session.bootstrap()
    await nextTick()

    expect(wrapper.get('[data-status]').text()).toBe('unavailable')
  })

  it('does not clear local authenticated state or report success when logout fails', async () => {
    vi.mocked(sessionApi.deleteSession).mockRejectedValue(new Error('offline'))
    const session = useSessionStore()
    session.setAuthenticatedUser(currentUser)

    await expect(session.logout()).rejects.toThrow('offline')

    expect(session.status).toBe('authenticated')
    expect(session.getUser).toEqual(currentUser)
    expect(notifySuccess).not.toHaveBeenCalled()
  })

  it('becomes anonymous only after server-side logout succeeds', async () => {
    vi.mocked(sessionApi.deleteSession).mockResolvedValue()
    const session = useSessionStore()
    session.setAuthenticatedUser(currentUser)

    await session.logout()

    expect(session.status).toBe('anonymous')
    expect(session.user).toBeNull()
    expect(notifySuccess).toHaveBeenCalledWith('Logout successful')
  })

  it('clears account-scoped feature state when the session becomes anonymous', () => {
    const session = useSessionStore()
    const dcc = useDccStore()
    dcc.jiraConnection = {
      state: 'connected',
      expires_at: '2099-01-01T00:00:00Z'
    }

    session.markAnonymous()

    expect(dcc.jiraConnection.state).toBe('disconnected')
  })

  it('clears account-scoped feature state before switching identities', () => {
    const session = useSessionStore()
    const dcc = useDccStore()
    session.setAuthenticatedUser(currentUser)
    dcc.jiraConnection = {
      state: 'connected',
      expires_at: '2099-01-01T00:00:00Z'
    }

    session.setAuthenticatedUser({ ...currentUser, id: 8, username: 'publisher' })

    expect(dcc.jiraConnection.state).toBe('disconnected')
    expect(session.getUser.username).toBe('publisher')
  })
})
