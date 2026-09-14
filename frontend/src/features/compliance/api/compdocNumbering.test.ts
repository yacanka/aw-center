import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
const mocks = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))
vi.mock('@/shared/api/http', () => ({ apiClient: mocks }))
import { fetchNumberingFormat } from './compdocNumbering'

describe('Numarator format discovery', () => {
  beforeEach(() => vi.resetAllMocks())
  afterEach(() => vi.useRealTimers())
  it('reads the worker artifact without contacting Numarator directly', async () => {
    mocks.post.mockResolvedValue({
      data: { id: 'job', status: 'succeeded', download_url: '/api/jobs/job/download/' }
    })
    const contract = {
      schema_version: 1,
      code: 'CP',
      fields: [{ key: 'department', required: false, default: 'GEN', max_length: 10 }]
    }
    mocks.get.mockResolvedValue({ data: contract })
    const signal = new AbortController().signal
    await expect(fetchNumberingFormat('ozgur', 'CP', signal)).resolves.toEqual(contract)
    expect(mocks.post).toHaveBeenCalledWith(
      'projects/ozgur/compliance-documents/numbering-options/',
      { client_operation_id: expect.any(String), format_code: 'CP' },
      { signal }
    )
    expect(mocks.get).toHaveBeenCalledWith('/api/jobs/job/download/', {
      responseType: 'json',
      signal
    })
  })
  it('does not silently treat failed discovery as a format without inputs', async () => {
    mocks.post.mockResolvedValue({ data: { status: 'failed', message: 'Format unavailable' } })
    await expect(fetchNumberingFormat('ozgur', 'CP', new AbortController().signal)).rejects.toThrow(
      'Format unavailable'
    )
    expect(mocks.get).not.toHaveBeenCalled()
  })
  it('stops polling when the format selection is cancelled', async () => {
    vi.useFakeTimers()
    mocks.post.mockResolvedValue({ data: { id: 'job', status: 'queued' } })
    const controller = new AbortController()
    const pending = fetchNumberingFormat('ozgur', 'CP', controller.signal)
    const rejected = expect(pending).rejects.toThrow('Cancelled')
    await Promise.resolve()
    controller.abort()
    await rejected
    await vi.advanceTimersByTimeAsync(2000)
    expect(mocks.get).not.toHaveBeenCalled()
  })
})
