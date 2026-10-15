import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { Job } from '@/features/jobs/api/jobs'

const http = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))
vi.mock('@/shared/api/http', () => ({ apiClient: http }))
import { enqueueDoorsModuleAttributes, fetchDoorsModuleAttributesResult } from './doorsAutomation'

describe('DOORS attribute discovery boundary', () => {
  const job = {
    kind: 'doors.run_dxl',
    status: 'succeeded',
    download_url: '/api/jobs/a/download/'
  } as Job
  const result = {
    type: 'doors_module_attributes',
    schema_version: 1,
    module_path: '/P/M',
    attributes: ['Identifier'],
    operation_result: {
      schema_version: 1,
      operation: 'list_attributes',
      outcome: 'success',
      code: 'LIST_ATTRIBUTES_DONE',
      input: { module_path: '/P/M' }
    }
  }
  beforeEach(() => vi.resetAllMocks())
  it('queues only a module path with an idempotency key', async () => {
    http.post.mockResolvedValue({ data: job })
    await enqueueDoorsModuleAttributes('/P/M', 'attempt')
    expect(http.post).toHaveBeenCalledWith(
      'integrations/doors/module-attributes-jobs/',
      { module_path: '/P/M' },
      { headers: { 'Idempotency-Key': 'attempt' } }
    )
  })
  it('reads a completed verified artifact and permits an empty list', async () => {
    http.get.mockResolvedValue({ data: result })
    await expect(fetchDoorsModuleAttributesResult(job)).resolves.toEqual(result)
    http.get.mockResolvedValue({ data: { ...result, attributes: [] } })
    await expect(fetchDoorsModuleAttributesResult(job)).resolves.toHaveProperty('attributes', [])
  })
  it.each([
    { ...result, type: 'doors_module_export' },
    { ...result, module_path: '/Other' },
    { ...result, attributes: ['Identifier', 'Identifier'] },
    { ...result, attributes: [''] },
    { ...result, attributes: Array.from({ length: 1001 }, (_, i) => `Name${i}`) },
    { ...result, attributes: [42] },
    { ...result, operation_result: { ...result.operation_result, operation: 'export_module' } }
  ])('rejects unsupported, mismatched or incomplete metadata', async (invalid) => {
    http.get.mockResolvedValue({ data: invalid })
    await expect(fetchDoorsModuleAttributesResult(job)).rejects.toThrow('invalid')
  })
  it('does not fetch non-successful or unrelated jobs', async () => {
    for (const invalid of [
      { ...job, status: 'running' },
      { ...job, kind: 'doors.update_object' },
      { ...job, download_url: null }
    ]) {
      await expect(fetchDoorsModuleAttributesResult(invalid as Job)).rejects.toThrow()
    }
    expect(http.get).not.toHaveBeenCalled()
  })
})
