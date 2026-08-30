import { describe, expect, it, vi } from 'vitest'
import { AxiosError, type AxiosAdapter, type AxiosResponse } from 'axios'
import { normalizeApiBaseUrl, normalizeApiRequestPath } from '@/shared/api/apiUrl'
import {
  API_BASE_URL,
  apiClient,
  cancelSessionScopedRequests,
  registerAuthenticationFailureHandler
} from '@/shared/api/http'

describe('API URL normalization', () => {
  it.each([
    [undefined, '/api/'],
    ['', '/api/'],
    ['/', '/api/'],
    ['/api', '/api/'],
    ['https://awcenter.example.com', 'https://awcenter.example.com/api/'],
    ['https://awcenter.example.com/', 'https://awcenter.example.com/api/'],
    ['https://awcenter.example.com/api/', 'https://awcenter.example.com/api/']
  ])('normalizes %s into the canonical API root', (configured, expected) => {
    expect(normalizeApiBaseUrl(configured)).toBe(expected)
  })

  it('rejects protocol-relative and credential-bearing configuration', () => {
    expect(() => normalizeApiBaseUrl('//attacker.test')).toThrow(/Protocol-relative/)
    expect(() => normalizeApiBaseUrl('https://user:pass@awcenter.test')).toThrow(/credentials/)
    expect(() => normalizeApiBaseUrl('/app?origin=attacker')).toThrow(/unsupported/)
    expect(() => normalizeApiBaseUrl('https://api.attacker.test', 'awcenter.example.com')).toThrow(
      /hostname/
    )
    expect(normalizeApiBaseUrl('http://127.0.0.1:8000', '127.0.0.1')).toBe(
      'http://127.0.0.1:8000/api/'
    )
  })

  it('normalizes server paths without allowing an absolute-host escape', () => {
    expect(normalizeApiRequestPath('/dcc/records/')).toBe('dcc/records/')
    expect(normalizeApiRequestPath('/api/dcc/records/')).toBe('dcc/records/')
    expect(() => normalizeApiRequestPath('//attacker.test/dcc')).toThrow(/relative path/)
    expect(() => normalizeApiRequestPath('\\\\attacker.test/dcc')).toThrow(/relative path/)
    expect(() => normalizeApiRequestPath('https://attacker.test/dcc')).toThrow(/relative path/)
    expect(() => normalizeApiRequestPath('jobs/../session/')).toThrow(/traversal/)
    expect(() => normalizeApiRequestPath('jobs/%2e%2e/session/')).toThrow(/traversal/)
    expect(() => normalizeApiRequestPath('jobs/%2Fadmin/')).toThrow(/encoded separators/)
  })
})

describe('shared API client', () => {
  it('normalizes a request before the adapter is invoked', async () => {
    const adapter = vi.fn(async (config) => ({
      config,
      data: null,
      headers: {},
      status: 200,
      statusText: 'OK'
    }))

    await apiClient.get('/api/dcc/records/', { adapter })

    expect(adapter).toHaveBeenCalledOnce()
    expect(adapter.mock.calls[0][0].baseURL).toBe(API_BASE_URL)
    expect(API_BASE_URL).toMatch(/\/api\/$/)
    expect(adapter.mock.calls[0][0].url).toBe('dcc/records/')
  })

  it('blocks a protocol-relative request before network dispatch', async () => {
    const adapter = vi.fn()
    await expect(apiClient.get('//attacker.test/dcc', { adapter })).rejects.toThrow(/relative path/)
    expect(adapter).not.toHaveBeenCalled()
  })

  it('blocks a backslash-based host escape before network dispatch', async () => {
    const adapter = vi.fn()
    await expect(apiClient.get('\\\\attacker.test/dcc', { adapter })).rejects.toThrow(
      /relative path/
    )
    expect(adapter).not.toHaveBeenCalled()
  })

  it('blocks encoded base-path traversal before network dispatch', async () => {
    const adapter = vi.fn()
    await expect(apiClient.get('jobs/%2e%2e/session/', { adapter })).rejects.toThrow(/traversal/)
    expect(adapter).not.toHaveBeenCalled()
  })

  it('cancels requests still owned by the previous browser session', async () => {
    const adapter: AxiosAdapter = vi.fn(
      (config) =>
        new Promise<AxiosResponse>((_resolve, reject) => {
          config.signal?.addEventListener?.('abort', () => reject(new Error('session changed')))
        })
    )
    const request = apiClient.get('jobs/', { adapter })

    await vi.waitFor(() => expect(adapter).toHaveBeenCalledOnce())
    cancelSessionScopedRequests()

    await expect(request).rejects.toThrow(/session changed|canceled/i)
  })

  it('invalidates only authentication failures, not ordinary permission denials', async () => {
    const handler = vi.fn()
    const unregister = registerAuthenticationFailureHandler(handler)

    await expect(
      apiClient.get('jobs/', { adapter: rejectingAdapter(403, 'FORBIDDEN') })
    ).rejects.toThrow()
    expect(handler).not.toHaveBeenCalled()

    await expect(
      apiClient.get('jobs/', { adapter: rejectingAdapter(403, 'NOT_AUTHENTICATED') })
    ).rejects.toThrow()
    expect(handler).toHaveBeenCalledOnce()
    unregister()
  })
})

function rejectingAdapter(status: number, code: string): AxiosAdapter {
  return async (config) => {
    const response: AxiosResponse = {
      config,
      data: { detail: 'Request denied.', code },
      headers: {},
      status,
      statusText: 'Forbidden'
    }
    throw new AxiosError('Request denied.', 'ERR_BAD_RESPONSE', config, undefined, response)
  }
}
