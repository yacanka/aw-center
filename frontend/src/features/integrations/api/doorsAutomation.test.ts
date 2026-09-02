import { beforeEach, describe, expect, it, vi } from 'vitest'

const http = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))
vi.mock('@/shared/api/http', () => ({ apiClient: http }))

import {
  enqueueDoorsModuleCheck,
  enqueueDoorsModuleExport,
  enqueueDoorsObjectCreate,
  enqueueDoorsObjectUpdate,
  enqueueDoorsRequirementLink,
  fetchDoorsRequirementLinkResult,
  fetchDoorsStatus
} from '@/features/integrations/api/doorsAutomation'

describe('DOORS durable automation API', () => {
  beforeEach(() => vi.clearAllMocks())

  it('uses the feature-aware fail-closed DOORS status resource', async () => {
    const status = {
      configured: true,
      available: false,
      active_runners: 0,
      transport: 'loopback_token'
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
})
