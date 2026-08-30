import type { RouteMeta, RouteRecordName } from 'vue-router'
import type { IUser } from '@/features/session/models/auth'
import {
  AUTHENTICATED_ACCESS,
  PUBLIC_ACCESS,
  resolveRouteAccess,
  type RouteAccessPolicy
} from '@/features/session/services/accessPolicy'
import type { SessionStatus } from '@/features/session/stores/session'

export interface SessionRouteTarget {
  name: RouteRecordName | null | undefined
  fullPath: string
  meta: RouteMeta
}

export interface SessionRouteState {
  status: SessionStatus
  isAuthenticated: boolean
  getUser: IUser
  bootstrap: (force?: boolean) => Promise<SessionStatus>
}

/** Resolve navigation only after protected-route session bootstrap has completed. */
export async function resolveSessionRoute(
  target: SessionRouteTarget,
  session: SessionRouteState
): Promise<true | { name: string; query?: Record<string, string> }> {
  if (target.meta.public) {
    if (target.name === 'login') await session.bootstrap(true)
    return target.name === 'login' && session.isAuthenticated ? { name: 'home' } : true
  }

  await session.bootstrap(true)
  const user = session.isAuthenticated ? session.getUser : null
  const decision = resolveRouteAccess(resolvePolicy(target.meta), user)
  if (decision === 'login') {
    return { name: 'login', query: { redirect: target.fullPath } }
  }
  if (decision === 'forbidden') {
    return { name: 'unauthorized', query: { from: target.fullPath } }
  }
  return true
}

function resolvePolicy(meta: RouteMeta): RouteAccessPolicy {
  if (meta.public) return PUBLIC_ACCESS
  return meta.access || AUTHENTICATED_ACCESS
}
