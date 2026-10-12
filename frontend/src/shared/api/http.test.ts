import { afterEach, describe, expect, it, vi } from 'vitest'
import { AxiosError, type AxiosAdapter } from 'axios'
import { apiClient, cancelSessionScopedRequests } from './http'

afterEach(() => {
  cancelSessionScopedRequests()
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

describe('request abort ownership', () => {
  it.each([
    'success',
    'network',
    'timeout',
    'pre-aborted',
    'malformed-cookie',
    'circular-json',
    'adapter-error'
  ] as const)('releases merged listeners after %s', async (outcome) => {
    const active = new Map<AbortSignal, Set<unknown>>()
    const originalAdd = AbortSignal.prototype.addEventListener
    const originalRemove = AbortSignal.prototype.removeEventListener
    vi.spyOn(AbortSignal.prototype, 'addEventListener').mockImplementation(function (
      this: AbortSignal,
      ...args: Parameters<AbortSignal['addEventListener']>
    ) {
      if (args[0] === 'abort') {
        const listeners = active.get(this) || new Set()
        listeners.add(args[1])
        active.set(this, listeners)
      }
      return originalAdd.apply(this, args)
    })
    vi.spyOn(AbortSignal.prototype, 'removeEventListener').mockImplementation(function (
      this: AbortSignal,
      ...args: Parameters<AbortSignal['removeEventListener']>
    ) {
      if (args[0] === 'abort') active.get(this)?.delete(args[1])
      return originalRemove.apply(this, args)
    })
    const controller = new AbortController()
    if (outcome === 'pre-aborted') controller.abort()
    if (outcome === 'malformed-cookie') vi.stubGlobal('document', { cookie: 'csrftoken=%' })
    const adapter: AxiosAdapter = async (config) => {
      if (outcome === 'adapter-error') throw new Error('Adapter failed before a response.')
      if (outcome === 'network' || outcome === 'timeout') {
        throw new AxiosError(
          'Request failed',
          outcome === 'timeout' ? 'ECONNABORTED' : 'ERR_NETWORK',
          config
        )
      }
      return { data: { ok: true }, status: 200, statusText: 'OK', headers: {}, config }
    }
    const circular: unknown[] = []
    circular.push(circular)
    const request = apiClient.post('test/', outcome === 'circular-json' ? circular : {}, {
      signal: controller.signal,
      adapter
    })
    if (outcome === 'success') expect((await request).data).toEqual({ ok: true })
    else await expect(request).rejects.toBeInstanceOf(Error)

    expect([...active.values()].reduce((count, listeners) => count + listeners.size, 0)).toBe(0)
  })

  it.each(['request', 'session'] as const)(
    'still cancels a pending request from its %s',
    async (source) => {
      const controller = new AbortController()
      let combined: AbortSignal | undefined
      let finish!: () => void
      const adapter: AxiosAdapter = async (config) => {
        combined = config.signal as AbortSignal
        await new Promise<void>((resolve) => (finish = resolve))
        return { data: {}, status: 200, statusText: 'OK', headers: {}, config }
      }
      const request = apiClient.get('test/', { signal: controller.signal, adapter })
      await Promise.resolve()
      await Promise.resolve()
      if (source === 'request') controller.abort()
      else cancelSessionScopedRequests()
      expect(combined?.aborted).toBe(true)
      finish()
      await expect(request).rejects.toMatchObject({ code: 'ERR_CANCELED' })
    }
  )
})
