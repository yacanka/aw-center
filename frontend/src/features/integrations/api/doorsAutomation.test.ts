import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { Job } from '@/features/jobs/api/jobs'

const http = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))
vi.mock('@/shared/api/http', () => ({ apiClient: http }))

import {
  enqueueDoorsModuleCheck,
  enqueueDoorsModuleExport,
  enqueueDoorsObjectCreate,
  enqueueDoorsObjectUpdate,
  enqueueDoorsRequirementLink,
  fetchDoorsRequirementLinkResult,
  fetchDoorsDeveloperResult,
  fetchDoorsStatus
} from '@/features/integrations/api/doorsAutomation'

describe('DOORS durable automation API', () => {
  beforeEach(() => vi.clearAllMocks())

  it('uses the feature-aware fail-closed DOORS status resource', async () => {
    const status = {
      configured: true,
      available: false,
      active_workers: 0,
      transport: 'windows-worker'
    }
    http.get.mockResolvedValue({ data: status })

    await expect(fetchDoorsStatus()).resolves.toBe(status)
    expect(http.get).toHaveBeenCalledWith('integrations/doors/status/')
  })

  it('queues operation-specific jobs with an idempotency key', async () => {
    const job = { id: 'job-1', kind: 'doors.run_dxl' }
    http.post.mockResolvedValue({ data: job })

    await expect(enqueueDoorsModuleCheck('/Project/Module', 'attempt-1')).resolves.toBe(job)
    await enqueueDoorsModuleExport('/Project/Module', 10000, 'attempt-export')
    await enqueueDoorsObjectUpdate(
      {
        module_path: '/Project/Module',
        absolute_number: 42,
        attributes: { Status: 'Approved' }
      },
      'attempt-2'
    )
    await enqueueDoorsObjectCreate(
      {
        module_path: '/Project/Module',
        position: 'after',
        relative_absolute_number: 42,
        attributes: { 'Object Heading': 'New requirement' }
      },
      'attempt-3'
    )
    await enqueueDoorsRequirementLink(
      {
        ref_module_name: '/Project/Reference',
        target_module_name: '/Project/Target',
        link_module_name: '/Project/Links',
        ref_attr_poc: 'PoC List',
        ref_attr_req: 'Requirement',
        target_attr_poc: 'PoC Info',
        start_index: 0,
        text_length: -1,
        direction: 'ref2tar',
        activeness: false
      },
      'attempt-4'
    )

    expect(http.post.mock.calls).toEqual([
      [
        'integrations/doors/module-check-jobs/',
        { module_path: '/Project/Module' },
        { headers: { 'Idempotency-Key': 'attempt-1' } }
      ],
      [
        'integrations/doors/module-export-jobs/',
        { module_path: '/Project/Module', limit: 10000 },
        { headers: { 'Idempotency-Key': 'attempt-export' } }
      ],
      [
        'integrations/doors/object-update-jobs/',
        {
          module_path: '/Project/Module',
          absolute_number: 42,
          attributes: { Status: 'Approved' }
        },
        { headers: { 'Idempotency-Key': 'attempt-2' } }
      ],
      [
        'integrations/doors/object-create-jobs/',
        {
          module_path: '/Project/Module',
          position: 'after',
          relative_absolute_number: 42,
          attributes: { 'Object Heading': 'New requirement' }
        },
        { headers: { 'Idempotency-Key': 'attempt-3' } }
      ],
      [
        'integrations/doors/requirement-link-jobs/',
        {
          ref_module_name: '/Project/Reference',
          target_module_name: '/Project/Target',
          link_module_name: '/Project/Links',
          ref_attr_poc: 'PoC List',
          ref_attr_req: 'Requirement',
          target_attr_poc: 'PoC Info',
          start_index: 0,
          text_length: -1,
          direction: 'ref2tar',
          activeness: false
        },
        { headers: { 'Idempotency-Key': 'attempt-4' } }
      ]
    ])
    expect(JSON.stringify(http.post.mock.calls)).not.toMatch(/JSESSIONID|run_dxl\/|objects\/update/)
  })

  it('reads a completed Linker result only from its owner-scoped job URL', async () => {
    const result = {
      type: 'doors_requirement_linker',
      schema_version: 1,
      mode: 'preview',
      direction: 'ref2tar',
      summary: {},
      groups: [],
      missing_targets: []
    }
    http.get.mockResolvedValue({ data: result })

    await expect(
      fetchDoorsRequirementLinkResult({
        kind: 'doors.link_requirements',
        download_url: '/api/jobs/job-1/download/'
      } as never)
    ).resolves.toBe(result)
    expect(http.get).toHaveBeenCalledWith('/api/jobs/job-1/download/', { responseType: 'json' })
  })

  it.each([true, false])(
    'reads the structured module accessibility result: %s',
    async (accessible) => {
      const result = moduleResult(accessible)
      http.get.mockResolvedValue({ data: result })
      await expect(fetchDoorsDeveloperResult(completedJob())).resolves.toEqual(result)
      expect(http.get).toHaveBeenCalledWith('/api/jobs/job-1/download/', { responseType: 'json' })
    }
  )

  it.each([
    null,
    { accessible: false },
    { ...moduleResult(false), accessible: true },
    {
      ...moduleResult(false),
      operation_result: { ...moduleResult(false).operation_result, schema_version: 2 }
    },
    {
      ...moduleResult(false),
      operation_result: { ...moduleResult(false).operation_result, operation: 'export_module' }
    },
    {
      ...moduleResult(false),
      operation_result: { ...moduleResult(false).operation_result, input: null }
    }
  ])('rejects malformed or mismatched result artifacts', async (data) => {
    http.get.mockResolvedValue({ data })
    await expect(fetchDoorsDeveloperResult(completedJob())).rejects.toThrow(
      'unsupported or invalid'
    )
  })

  it('does not fetch artifacts for unfinished or unrelated jobs', async () => {
    for (const overrides of [
      { status: 'running' },
      { kind: 'doors.link_requirements' },
      { download_url: null }
    ]) {
      await expect(
        fetchDoorsDeveloperResult({ ...completedJob(), ...overrides } as never)
      ).rejects.toThrow('unavailable')
    }
    expect(http.get).not.toHaveBeenCalled()
  })

  it('validates object identities before they can be used as another input', async () => {
    const result = {
      absolute_number: 42,
      updated: true,
      operation_result: {
        schema_version: 1,
        operation: 'update_object',
        outcome: 'success',
        code: 'ATTRIBUTES_SAVED',
        message: 'Object attributes saved.',
        input: { module_path: '/Project/Module', absolute_number: 42 }
      }
    }
    const job = { ...completedJob(), kind: 'doors.update_object' }
    http.get.mockResolvedValue({ data: result })
    await expect(fetchDoorsDeveloperResult(job)).resolves.toEqual(result)
    for (const absolute_number of [0, 1.5, '42', 43]) {
      http.get.mockResolvedValue({ data: { ...result, absolute_number } })
      await expect(fetchDoorsDeveloperResult(job)).rejects.toThrow('unsupported or invalid')
    }
  })
})

function completedJob() {
  return {
    kind: 'doors.run_dxl',
    status: 'succeeded',
    download_url: '/api/jobs/job-1/download/'
  } as Job
}

function moduleResult(accessible: boolean) {
  return {
    accessible,
    module_path: '/Project/Module',
    operation_result: {
      schema_version: 1,
      operation: 'check_module',
      outcome: accessible ? 'success' : 'negative',
      code: accessible ? 'MODULE_OPENED' : 'OPEN_MODULE',
      message: accessible ? 'Module found and readable.' : 'Module not found or no read access.',
      input: { module_path: '/Project/Module' }
    }
  }
}
