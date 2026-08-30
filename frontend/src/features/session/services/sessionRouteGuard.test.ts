import { describe, expect, it, vi } from 'vitest'
import {
  resolveSessionRoute,
  type SessionRouteState
} from '@/features/session/services/sessionRouteGuard'
import type { SessionStatus } from '@/features/session/stores/session'

describe('session route guard', () => {
  it('awaits protected-route bootstrap before making the access decision', async () => {
    const session: SessionRouteState = {
      status: 'unknown',
      isAuthenticated: false,
      getUser: {},
      bootstrap: vi.fn(async () => {
        session.status = 'authenticated'
        session.isAuthenticated = true
        session.getUser = { id: 9, is_active: true }
        return session.status
      })
    }

    await expect(
      resolveSessionRoute({ name: 'jobs', fullPath: '/jobs?page=2', meta: {} }, session)
    ).resolves.toBe(true)
    expect(session.bootstrap).toHaveBeenCalledOnce()
    expect(session.bootstrap).toHaveBeenCalledWith(true)
  })

  it('preserves the protected deep link when the server has no session', async () => {
    const session: SessionRouteState = {
      status: 'anonymous',
      isAuthenticated: false,
      getUser: {},
      bootstrap: vi.fn(async (): Promise<SessionStatus> => 'anonymous')
    }

    await expect(
      resolveSessionRoute({ name: 'jobs', fullPath: '/jobs?page=2', meta: {} }, session)
    ).resolves.toEqual({ name: 'login', query: { redirect: '/jobs?page=2' } })
    expect(session.bootstrap).toHaveBeenCalledWith(true)
  })

  it('does not block a public welcome route on session I/O', async () => {
    const session: SessionRouteState = {
      status: 'unknown',
      isAuthenticated: false,
      getUser: {},
      bootstrap: vi.fn(async (): Promise<SessionStatus> => 'anonymous')
    }

    await expect(
      resolveSessionRoute(
        { name: 'welcome', fullPath: '/welcome', meta: { public: true } },
        session
      )
    ).resolves.toBe(true)
    expect(session.bootstrap).not.toHaveBeenCalled()
  })
})
