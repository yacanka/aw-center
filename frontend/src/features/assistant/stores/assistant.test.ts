// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { createApp } from 'vue'

vi.mock('@/features/assistant/api/assistant', async (importOriginal) => ({
  ...(await importOriginal<object>()),
  fetchAssistantCatalog: vi.fn(),
  sendAssistantMessage: vi.fn()
}))
vi.mock('@/shared/services/notify', () => ({ notifyError: vi.fn(), notifySuccess: vi.fn() }))
import * as api from '@/features/assistant/api/assistant'
import { useAssistantStore } from './assistant'
import { registerSessionScopedStore } from '@/features/session/stores/sessionScope'
import { useSessionStore } from '@/features/session/stores/session'

const reply = {
  answer: 'Help',
  applications: [
    { id: 'compare', title: 'Compare', path: '/compare', description: 'Compare documents.' }
  ],
  sources: [{ id: 'compare', title: 'Compare guide', path: '/compare' }]
}
function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (error: unknown) => void
  const promise = new Promise<T>((yes, no) => {
    resolve = yes
    reject = no
  })
  return { promise, resolve, reject }
}
function setupPinia() {
  const pinia = createPinia()
  pinia.use(registerSessionScopedStore)
  createApp({}).use(pinia)
  setActivePinia(pinia)
  return pinia
}

describe('session-scoped assistant conversation', () => {
  beforeEach(() => {
    setupPinia()
    vi.clearAllMocks()
    vi.mocked(api.sendAssistantMessage).mockResolvedValue(reply)
    vi.mocked(api.fetchAssistantCatalog).mockResolvedValue({
      status: 'configured',
      applications: reply.applications
    })
  })

  it('retains server cards but sends only role/content as history', async () => {
    const store = useAssistantStore()
    await store.send('Hello', '/home')
    expect(store.messages[1]).toMatchObject({
      role: 'assistant',
      content: 'Help',
      applications: reply.applications,
      sources: reply.sources
    })
    await store.send('More', '/compare?filter=private')
    expect(api.sendAssistantMessage).toHaveBeenLastCalledWith(
      {
        message: 'More',
        history: [
          { role: 'user', content: 'Hello' },
          { role: 'assistant', content: 'Help' }
        ],
        current_path: '/compare'
      },
      expect.any(AbortSignal)
    )
  })

  it('blocks same-store simultaneous sends and invalid messages', async () => {
    const request = deferred<typeof reply>()
    vi.mocked(api.sendAssistantMessage).mockReturnValue(request.promise)
    const store = useAssistantStore()
    const first = store.send('Hello', '/home')
    expect(await store.send('Second', '/home')).toBe(false)
    expect(store.messages).toHaveLength(1)
    request.resolve(reply)
    await first
    expect(await store.send('😀'.repeat(4001), '/home')).toBe(false)
    expect(api.sendAssistantMessage).toHaveBeenCalledOnce()
    expect(store.error).toContain('4,000')
  })

  it('retries the failed request without duplicating the user turn or including it in history', async () => {
    vi.mocked(api.sendAssistantMessage).mockRejectedValueOnce({
      response: { data: { detail: 'Try later.', code: 'THROTTLED', request_id: 'request-1' } }
    })
    const store = useAssistantStore()
    await store.send('Help', '/home')
    expect(store.errorCode).toBe('THROTTLED')
    expect(store.error).toContain('request-1')
    await store.retry()
    expect(store.messages.map((row) => row.role)).toEqual(['user', 'assistant'])
    expect(api.sendAssistantMessage).toHaveBeenLastCalledWith(
      { message: 'Help', history: [], current_path: '/home' },
      expect.any(AbortSignal)
    )
  })

  it.each(['resetConversation', '$reset'] as const)(
    'fences a stale result and finally after %s and a fresh send',
    async (reset) => {
      const old = deferred<typeof reply>()
      const fresh = deferred<typeof reply>()
      vi.mocked(api.sendAssistantMessage)
        .mockReturnValueOnce(old.promise)
        .mockReturnValueOnce(fresh.promise)
      const store = useAssistantStore()
      const a = store.send('Old', '/home')
      const signal = vi.mocked(api.sendAssistantMessage).mock.calls[0]?.[1]
      store[reset]()
      expect(signal?.aborted).toBe(true)
      const b = store.send('New', '/home')
      old.resolve({ ...reply, answer: 'old reply' })
      await a
      expect(store.pending).toBe(true)
      expect(store.messages.some((row) => row.content === 'old reply')).toBe(false)
      fresh.resolve(reply)
      await b
      expect(store.pending).toBe(false)
      expect(store.messages.map((row) => row.content)).toEqual(['New', 'Help'])
    }
  )

  it('ignores stale chat failures after a reset', async () => {
    const request = deferred<typeof reply>()
    vi.mocked(api.sendAssistantMessage).mockReturnValue(request.promise)
    const store = useAssistantStore()
    const pending = store.send('Old', '/home')
    store.$reset()
    request.reject(new Error('old failure'))
    await pending
    expect(store.error).toBe('')
    expect(store.messages).toEqual([])
  })

  it('loads the catalog once and fences old catalog results and finally on session reset', async () => {
    const old = deferred<api.AssistantCatalog>()
    const fresh = deferred<api.AssistantCatalog>()
    vi.mocked(api.fetchAssistantCatalog)
      .mockReturnValueOnce(old.promise)
      .mockReturnValueOnce(fresh.promise)
    const session = useSessionStore()
    session.setAuthenticatedUser({ id: 7 })
    const store = useAssistantStore()
    const a = store.loadCatalog()
    const signal = vi.mocked(api.fetchAssistantCatalog).mock.calls[0]?.[0]
    session.setAuthenticatedUser({ id: 8 })
    expect(signal?.aborted).toBe(true)
    const b = store.loadCatalog()
    old.resolve({ status: 'configured', applications: reply.applications })
    await a
    expect(store.catalogPending).toBe(true)
    expect(store.catalog).toBeNull()
    fresh.resolve({ status: 'unconfigured', applications: [] })
    await b
    await store.loadCatalog()
    expect(store.catalog?.status).toBe('unconfigured')
    expect(api.fetchAssistantCatalog).toHaveBeenCalledTimes(2)
  })

  it.each(['markAnonymous', 'changeUser'])(
    'real session plugin aborts chat and clears state on %s',
    async (change) => {
      const session = useSessionStore()
      session.setAuthenticatedUser({ id: 7 })
      const store = useAssistantStore()
      const old = deferred<typeof reply>()
      vi.mocked(api.sendAssistantMessage).mockReturnValue(old.promise)
      const a = store.send('Old', '/home')
      const signal = vi.mocked(api.sendAssistantMessage).mock.calls[0]?.[1]
      if (change === 'markAnonymous') session.markAnonymous()
      else session.setAuthenticatedUser({ id: 8 })
      expect(signal?.aborted).toBe(true)
      expect(store.messages).toEqual([])
      expect(store.pending).toBe(false)
      old.resolve(reply)
      await a
      expect(store.messages).toEqual([])
    }
  )

  it('owns request controllers per Pinia instance', async () => {
    const first = deferred<typeof reply>()
    const second = deferred<typeof reply>()
    vi.mocked(api.sendAssistantMessage)
      .mockReturnValueOnce(first.promise)
      .mockReturnValueOnce(second.promise)
    const a = useAssistantStore()
    const pendingA = a.send('A', '/home')
    setupPinia()
    const b = useAssistantStore()
    const pendingB = b.send('B', '/home')
    a.$reset()
    expect(vi.mocked(api.sendAssistantMessage).mock.calls[1]?.[1]?.aborted).toBe(false)
    first.resolve(reply)
    second.resolve(reply)
    await Promise.all([pendingA, pendingB])
    expect(a.messages).toEqual([])
    expect(b.messages.map((row) => row.content)).toEqual(['B', 'Help'])
  })

  it('ignores stale catalog errors after reset while a fresh catalog request is pending', async () => {
    const old = deferred<api.AssistantCatalog>()
    const fresh = deferred<api.AssistantCatalog>()
    vi.mocked(api.fetchAssistantCatalog)
      .mockReturnValueOnce(old.promise)
      .mockReturnValueOnce(fresh.promise)
    const store = useAssistantStore()
    const a = store.loadCatalog()
    await store.loadCatalog()
    expect(api.fetchAssistantCatalog).toHaveBeenCalledOnce()
    store.$reset()
    const b = store.loadCatalog()
    old.reject(new Error('Old catalog error'))
    await a
    expect(store.catalogError).toBe('')
    expect(store.catalogPending).toBe(true)
    fresh.resolve({ status: 'configured', applications: [] })
    await b
    expect(store.catalog?.status).toBe('configured')
  })
})
