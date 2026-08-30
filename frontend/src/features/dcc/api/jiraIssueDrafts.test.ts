import { beforeEach, describe, expect, it, vi } from 'vitest'

const http = vi.hoisted(() => ({ get: vi.fn(), patch: vi.fn(), post: vi.fn() }))
vi.mock('@/shared/api/http', () => ({ apiClient: http }))

import {
  createJiraIssueDraft,
  preflightJiraIssueDraft,
  publishJiraIssueDraft,
  type JiraIssueDraft
} from '@/features/dcc/api/jiraIssueDrafts'

describe('JIRA issue draft API', () => {
  beforeEach(() => vi.clearAllMocks())

  it('creates a draft with public project slugs rather than database identifiers', async () => {
    const draft = { id: 'draft-1', project_slugs: ['ozgur'] }
    http.post.mockResolvedValue({ data: draft })

    await expect(createJiraIssueDraft('job-1', ['ozgur'])).resolves.toBe(draft)
    expect(http.post).toHaveBeenCalledWith('dcc/issue-drafts/', {
      source_job_id: 'job-1',
      project_slugs: ['ozgur']
    })
  })

  it('version-checks preflight and queues publication without a browser credential', async () => {
    const draft = {
      id: 'draft-1',
      version: 7,
      status: 'reconciliation_required'
    } as JiraIssueDraft
    const preflight = { ready: true }
    const job = { id: 'job-2', kind: 'dcc.publish_jira_draft' }
    http.post.mockResolvedValueOnce({ data: preflight }).mockResolvedValueOnce({ data: job })

    await expect(preflightJiraIssueDraft(draft)).resolves.toBe(preflight)
    await expect(publishJiraIssueDraft(draft, 'publish-attempt')).resolves.toBe(job)

    expect(http.post.mock.calls).toEqual([
      ['dcc/issue-drafts/draft-1/preflight/', { version: 7 }],
      [
        'dcc/issue-drafts/draft-1/publish/',
        { version: 7, reconcile: true },
        { headers: { 'Idempotency-Key': 'publish-attempt' } }
      ]
    ])
    expect(JSON.stringify(http.post.mock.calls)).not.toMatch(/JSESSIONID|credential/i)
  })
})
