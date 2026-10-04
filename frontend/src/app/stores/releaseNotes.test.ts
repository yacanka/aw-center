import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

vi.mock('@/shared/api/http', () => ({
  apiClient: { get: vi.fn(), post: vi.fn() }
}))

import { apiClient } from '@/shared/api/http'
import { useReleaseNotesStore } from './releaseNotes'

const latest = { id: 2501, version: '1.0', title: 'Release', requires_ack: false, items: [] }

describe('release note acknowledgement batches', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.resetAllMocks()
  })

  it('marks every unseen note through bounded requests and checks once per session', async () => {
    const ids = Array.from({ length: 2501 }, (_, index) => index + 1)
    const seen = new Set<number>()
    const batchSizes: number[] = []
    vi.mocked(apiClient.get).mockResolvedValue({ data: { latest, mark_seen_ids: ids } })
    vi.mocked(apiClient.post).mockImplementation(async (_url, payload) => {
      const batch = (payload as { ids: number[] }).ids
      if (batch.length > 1000) throw new Error('Release batch exceeds the API limit')
      batchSizes.push(batch.length)
      for (const id of batch) seen.add(id)
      return { data: { ok: true, created: batch.length } }
    })
    const log = vi.spyOn(console, 'error').mockImplementation(() => {})
    try {
      const store = useReleaseNotesStore()
      await store.checkUnseen()
      await store.checkUnseen()

      expect([...seen]).toEqual(ids)
      expect(batchSizes).toEqual([1000, 1000, 501])
      expect(store.current).toEqual(latest)
      expect(store.unseen_ids).toEqual(ids)
      expect(store.show).toBe(true)
      expect(store.loading).toBe(false)
    } finally {
      log.mockRestore()
    }
  })

  it('sends exactly one request at the API limit', async () => {
    const ids = Array.from({ length: 1000 }, (_, index) => index + 1)
    vi.mocked(apiClient.get).mockResolvedValue({ data: { latest, mark_seen_ids: ids } })
    vi.mocked(apiClient.post).mockResolvedValue({ data: { ok: true, created: 1000 } })

    await useReleaseNotesStore().checkUnseen()

    expect(apiClient.post).toHaveBeenCalledExactlyOnceWith('releases/release-notes/bulk-seen', {
      ids
    })
  })

  it('stops submitting later batches after an HTTP failure and clears loading', async () => {
    const ids = Array.from({ length: 2501 }, (_, index) => index + 1)
    const seen = new Set<number>()
    let attempts = 0
    vi.mocked(apiClient.get).mockResolvedValue({ data: { latest, mark_seen_ids: ids } })
    vi.mocked(apiClient.post).mockImplementation(async (_url, payload) => {
      attempts += 1
      if (attempts === 2) throw new Error('Synthetic HTTP failure')
      for (const id of (payload as { ids: number[] }).ids) seen.add(id)
      return { data: { ok: true } }
    })
    const log = vi.spyOn(console, 'error').mockImplementation(() => {})
    try {
      const store = useReleaseNotesStore()
      await store.checkUnseen()

      expect(attempts).toBe(2)
      expect([...seen]).toEqual(ids.slice(0, 1000))
      expect(store.loading).toBe(false)
    } finally {
      log.mockRestore()
    }
  })

  it('does not submit when the server returns no unseen notes', async () => {
    vi.mocked(apiClient.get).mockResolvedValue({ status: 204, data: undefined })
    const store = useReleaseNotesStore()

    await store.checkUnseen()

    expect(store.current).toBeNull()
    expect(store.show).toBe(false)
    expect(store.loading).toBe(false)
    expect(apiClient.post).not.toHaveBeenCalled()
  })
})
