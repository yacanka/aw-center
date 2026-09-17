import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { Job } from '@/features/jobs/api/jobs'

const http = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))
vi.mock('@/shared/api/http', () => ({ apiClient: http }))
import { enqueueDoorsQualityCheck, fetchDoorsQualityResult } from './doorsQuality'

export function report() {
  return {
    type: 'doors_module_quality',
    schema_version: 1,
    module_path: '/Project/Module',
    outcome: 'passed',
    complete: true,
    attributes: {
      ata: { name: 'ATA Chapter', method: 'exact', candidates: ['ATA Chapter'] },
      panel: { name: 'Panel', method: 'exact', candidates: ['Panel'] }
    },
    warnings: [],
    findings: [],
    summary: {
      scanned_objects: 2,
      checked_objects: 2,
      unassigned_objects: 0,
      unresolved_objects: 0,
      conflicting_chapters: 0,
      chapters: 1,
      finding_count: 0,
      omitted_findings: 0
    }
  }
}
const job = {
  kind: 'doors.check_module_quality',
  status: 'succeeded',
  download_url: '/api/jobs/1/download/'
} as Job

describe('DOORS quality report API', () => {
  beforeEach(() => vi.resetAllMocks())
  it('queues a fixed task with a stable idempotency key', async () => {
    http.post.mockResolvedValue({ data: job })
    await expect(enqueueDoorsQualityCheck('/P/M', 'attempt')).resolves.toBe(job)
    expect(http.post).toHaveBeenCalledWith(
      'integrations/doors/module-quality-jobs/',
      { module_path: '/P/M' },
      { headers: { 'Idempotency-Key': 'attempt' } }
    )
  })
  it('loads only completed quality reports', async () => {
    http.get.mockResolvedValue({ data: report() })
    await expect(fetchDoorsQualityResult(job)).resolves.toEqual(report())
    expect(http.get).toHaveBeenCalledWith(job.download_url, { responseType: 'json' })
    http.get.mockClear()
    for (const overrides of [
      { status: 'running' },
      { kind: 'doors.run_dxl' },
      { download_url: null }
    ]) {
      await expect(fetchDoorsQualityResult({ ...job, ...overrides } as Job)).rejects.toThrow(
        'unavailable'
      )
    }
    expect(http.get).not.toHaveBeenCalled()
  })
  it.each([
    null,
    { ...report(), schema_version: 2 },
    { ...report(), attributes: {} },
    { ...report(), summary: {} },
    { ...report(), findings: [{}] },
    { ...report(), complete: false },
    { ...report(), summary: { ...report().summary, finding_count: 1 } }
  ])('rejects malformed or misleading success reports', async (data) => {
    http.get.mockResolvedValue({ data })
    await expect(fetchDoorsQualityResult(job)).rejects.toThrow('invalid or unsupported')
  })
})
