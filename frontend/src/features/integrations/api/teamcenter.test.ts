import { beforeEach, describe, expect, it, vi } from 'vitest'

const http = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))
vi.mock('@/shared/api/http', () => ({ apiClient: http }))

import { enqueueTeamcenterPropertyUpdate } from '@/features/integrations/api/teamcenter'

describe('Teamcenter durable mutations', () => {
  beforeEach(() => vi.clearAllMocks())

  it('queues property writes with the canonical body and idempotency header', async () => {
    const job = { id: 'job-1', kind: 'teamcenter.update_properties' }
    const updates = [
      {
        object: { uid: 'UID-1', type: 'WorkspaceObject' },
        properties: { object_name: ['Reviewed'] }
      }
    ]
    http.post.mockResolvedValue({ data: job })

    await expect(enqueueTeamcenterPropertyUpdate(updates, 'attempt-1')).resolves.toBe(job)
    expect(http.post).toHaveBeenCalledWith(
      'integrations/teamcenter/property-update-jobs/',
      { updates },
      { headers: { 'Idempotency-Key': 'attempt-1' } }
    )
  })
})
