import { beforeEach, describe, expect, it, vi } from 'vitest'

const http = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), delete: vi.fn() }))
vi.mock('@/shared/api/http', () => ({ apiClient: http }))

import { connectJira } from './jiraSession'

describe('Jira credential exchange', () => {
  beforeEach(() => vi.clearAllMocks())

  it('sends only the selected credential to the canonical POST resource', async () => {
    const connection = {
      state: 'connected',
      user: { username: 'operator', display_name: 'Operator' },
      expires_at: '2027-01-01T00:00:00Z'
    }
    http.post.mockResolvedValue({ data: connection })

    await expect(connectJira('fixture-token', 'personal_access_token')).resolves.toEqual(connection)
    await expect(connectJira('fixture-session', 'session_id')).resolves.toEqual(connection)
    expect(http.post.mock.calls).toEqual([
      ['integrations/jira/session/', { personal_access_token: 'fixture-token' }],
      ['integrations/jira/session/', { JSESSIONID: 'fixture-session' }]
    ])
  })
})
