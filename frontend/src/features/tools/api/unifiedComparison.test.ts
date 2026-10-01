import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/shared/api/http', () => ({ apiClient: { post: vi.fn(), get: vi.fn() } }))
import { apiClient } from '@/shared/api/http'
import { comparisonFamily, enqueueComparison, type ComparisonOptions } from './unifiedComparison'

const options: ComparisonOptions = {
  preset: 'balanced',
  equal_ratio: 0.92,
  weak_equal_ratio: 0.7,
  output_type: 'word'
}

describe('unified comparison API', () => {
  beforeEach(() => vi.clearAllMocks())
  it('recognizes only the supported file families', () => {
    expect(comparisonFamily('Report.DOCM')).toBe('word')
    expect(comparisonFamily('Data.xlsx')).toBe('excel')
    expect(comparisonFamily('Scan.pdf')).toBe('pdf')
    expect(comparisonFamily('Data.xls')).toBeNull()
  })
  it('sends two files and a stable caller-owned idempotency key', async () => {
    vi.mocked(apiClient.post).mockResolvedValue({ data: { id: 'job' } })
    const files: [File, File] = [new File(['a'], 'a.docx'), new File(['b'], 'b.docx')]
    await enqueueComparison(false, { files }, options, 'stable-request-key')
    const [path, body, config] = vi.mocked(apiClient.post).mock.calls[0]
    expect(path).toBe('tools/compare/jobs/')
    expect((body as FormData).get('first')).toBe(files[0])
    expect((body as FormData).get('second')).toBe(files[1])
    expect(config?.headers).toEqual({ 'Idempotency-Key': 'stable-request-key' })
  })
  it('reuses an inspection without uploading the files again', async () => {
    vi.mocked(apiClient.post).mockResolvedValue({ data: { id: 'job' } })
    await enqueueComparison(false, { inspectionId: 'inspection-id' }, options, 'stable-request-key')
    const body = vi.mocked(apiClient.post).mock.calls[0][1] as FormData
    expect(body.get('inspection_id')).toBe('inspection-id')
    expect(body.has('first')).toBe(false)
  })
})
