import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/shared/api/http', () => ({ apiClient: { get: vi.fn(), post: vi.fn() } }))
import { apiClient } from '@/shared/api/http'
import { fetchAssistantCatalog, sendAssistantMessage, type AssistantRequest } from './assistant'

function requestBody(index = 0): AssistantRequest {
  return vi.mocked(apiClient.post).mock.calls[index]?.[1] as AssistantRequest
}

describe('assistant API boundary', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(apiClient.post).mockResolvedValue({
      data: { answer: 'Help', applications: [], sources: [] }
    })
  })

  it('uses the authenticated catalog with the caller cancellation signal', async () => {
    const catalog = { status: 'unconfigured', applications: [] }
    vi.mocked(apiClient.get).mockResolvedValue({ data: catalog })
    const signal = new AbortController().signal
    expect(await fetchAssistantCatalog(signal)).toEqual(catalog)
    expect(apiClient.get).toHaveBeenCalledWith('integrations/assistant/catalog/', { signal })
  })

  it('sends only conversation fields and strips history metadata and URL state', async () => {
    const signal = new AbortController().signal
    await sendAssistantMessage(
      {
        message: 'Help',
        history: [{ role: 'user', content: 'Earlier', applications: [] }],
        current_path: '/compare?secret=private#detail',
        token: 'client-owned',
        model: 'other'
      } as never,
      signal
    )
    expect(apiClient.post).toHaveBeenCalledWith(
      'integrations/assistant/chat/',
      {
        message: 'Help',
        history: [{ role: 'user', content: 'Earlier' }],
        current_path: '/compare'
      },
      { signal, timeout: 35000 }
    )
  })

  it('keeps the latest twelve whole history messages', async () => {
    const history = Array.from({ length: 14 }, (_, i) => ({
      role: 'user' as const,
      content: String(i)
    }))
    await sendAssistantMessage({ message: 'Help', history, current_path: '/home' })
    expect(requestBody().history).toEqual(history.slice(2))
  })

  it('counts Unicode code points like Python and drops whole old messages at 24000', async () => {
    const history = [
      { role: 'user' as const, content: '😀'.repeat(6000) },
      { role: 'assistant' as const, content: 'a'.repeat(18000) }
    ]
    await sendAssistantMessage({ message: '😀'.repeat(4000), history, current_path: '/home' })
    expect(requestBody().history).toEqual(history)
    await sendAssistantMessage({
      message: 'Help',
      history: [...history, { role: 'user', content: 'x' }],
      current_path: '/home'
    })
    expect(requestBody(1).history).toEqual(history.slice(1).concat({ role: 'user', content: 'x' }))
  })

  it('measures actual UTF-8 JSON bytes including escaping before dropping old history', async () => {
    const history = Array.from({ length: 12 }, () => ({
      role: 'assistant' as const,
      content: '\u0000'.repeat(2000)
    }))
    await sendAssistantMessage({ message: '😀'.repeat(4000), history, current_path: '/home' })
    const body = requestBody()
    expect(new TextEncoder().encode(JSON.stringify(body)).byteLength).toBeLessThanOrEqual(65536)
    expect(body.history.length).toBeGreaterThan(0)
    expect(body.history.length).toBeLessThan(12)
    expect(body.history.every((row: { content: string }) => row.content.length === 2000)).toBe(true)
  })

  it.each(['', '  ', 'a'.repeat(4001), '😀'.repeat(4001)])(
    'rejects invalid messages without HTTP',
    async (message) => {
      await expect(
        sendAssistantMessage({ message, history: [], current_path: '/home' })
      ).rejects.toThrow()
      expect(apiClient.post).not.toHaveBeenCalled()
    }
  )
})
