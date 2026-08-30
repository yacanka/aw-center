import { beforeEach, describe, expect, it, vi } from 'vitest'

const http = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))
vi.mock('@/shared/api/http', () => ({ apiClient: http }))

import {
  approveEcrWorkflow,
  createEcrWorkflow,
  preflightEcrWorkflow,
  resumeEcrWorkflow,
  type EcrWorkflow
} from '@/features/dcc/api/ecrWorkflows'

describe('ECR workflow API', () => {
  beforeEach(() => vi.clearAllMocks())

  it('creates an immutable PDF review with project slugs and an idempotency key', async () => {
    const workflow = { id: 'ecr-1' }
    http.post.mockResolvedValue({ data: workflow })
    const file = new File(['review'], 'review.pdf', { type: 'application/pdf' })

    await expect(createEcrWorkflow(file, ['aesa'], 'create-key')).resolves.toBe(workflow)

    const [path, body, config] = http.post.mock.calls[0]
    expect(path).toBe('workflows/ecr/')
    expect(body).toBeInstanceOf(FormData)
    expect(body.get('file')).toBe(file)
    expect(body.get('project_slugs')).toBe('["aesa"]')
    expect(config).toEqual({ headers: { 'Idempotency-Key': 'create-key' } })
  })

  it('approves the reviewed version with a bounded server publication plan', async () => {
    const workflow = { id: 'ecr-1', version: 7 } as EcrWorkflow
    const approved = { id: 'ecr-1', version: 8 }
    http.post.mockResolvedValue({ data: approved })

    await expect(
      approveEcrWorkflow(workflow, {
        project_key: 'AWC',
        subtasks: [
          {
            summary: 'Review effectivity',
            description: '',
            assignee: '',
            priority: '',
            due_date: null
          }
        ]
      })
    ).resolves.toBe(approved)

    expect(http.post).toHaveBeenCalledWith('workflows/ecr/ecr-1/approve/', {
      version: 7,
      project_key: 'AWC',
      extra_fields: {},
      subtasks: [
        {
          summary: 'Review effectivity',
          description: '',
          assignee: '',
          priority: '',
          due_date: null
        }
      ]
    })
  })

  it('preflights the exact unapproved plan without browser credentials', async () => {
    const workflow = { id: 'ecr-1', version: 7 } as EcrWorkflow
    const result = { ready: true }
    http.post.mockResolvedValue({ data: result })

    await expect(
      preflightEcrWorkflow(workflow, {
        project_key: 'AWC',
        extra_fields: { customfield_123: 'Certification' },
        subtasks: []
      })
    ).resolves.toBe(result)

    expect(http.post).toHaveBeenCalledWith('workflows/ecr/ecr-1/preflight/', {
      version: 7,
      project_key: 'AWC',
      extra_fields: { customfield_123: 'Certification' },
      subtasks: []
    })
  })

  it('resumes with optimistic versioning and no browser-side credential', async () => {
    const workflow = { id: 'ecr-1', version: 11 } as EcrWorkflow
    http.post.mockResolvedValue({ data: workflow })

    await resumeEcrWorkflow(workflow, 'resume-key')

    expect(http.post).toHaveBeenCalledWith(
      'workflows/ecr/ecr-1/resume/',
      { version: 11 },
      { headers: { 'Idempotency-Key': 'resume-key' } }
    )
    expect(JSON.stringify(http.post.mock.calls)).not.toMatch(/JSESSIONID|credential/i)
  })
})
