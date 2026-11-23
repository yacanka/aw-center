import { describe, expect, it, vi } from 'vitest'
import {
  resolveSessionRoute,
  type SessionRouteState
} from '@/features/session/services/sessionRouteGuard'
import type { SessionStatus } from '@/features/session/stores/session'

const dashboardSession: SessionRouteState = {
  status: 'authenticated',
  isAuthenticated: true,
  getUser: { id: 9, is_active: true, is_staff: true, dashboard_only: true },
  bootstrap: async () => 'authenticated'
}

describe('session route guard', () => {
  it('sends an existing Dashboard User session from login to the certification home', async () => {
    await expect(
      resolveSessionRoute(
        { name: 'login', fullPath: '/login', meta: { public: true } },
        dashboardSession
      )
    ).resolves.toEqual({ name: 'compdocsHome' })
  })

  it('redirects a Dashboard User away from other AW Center modules', async () => {
    await expect(
      resolveSessionRoute({ name: 'jobs', fullPath: '/jobs', meta: {} }, dashboardSession)
    ).resolves.toEqual({ name: 'compdocsHome' })
  })

  it('allows a Dashboard User to reopen a certification project deep link', async () => {
    await expect(
      resolveSessionRoute(
        {
          name: 'certificationProject',
          fullPath: '/compdocs/aksungur/dashboard',
          meta: { certification: true }
        },
        dashboardSession
      )
    ).resolves.toBe(true)
  })

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

  it('does not block a public invitation route on session I/O', async () => {
    const session: SessionRouteState = {
      status: 'unknown',
      isAuthenticated: false,
      getUser: {},
      bootstrap: vi.fn(async (): Promise<SessionStatus> => 'anonymous')
    }

    await expect(
      resolveSessionRoute(
        { name: 'invitation', fullPath: '/invite', meta: { public: true } },
        session
      )
    ).resolves.toBe(true)
    expect(session.bootstrap).not.toHaveBeenCalled()
  })
})
