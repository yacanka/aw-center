import { createRouter, createWebHistory, type RouteMeta } from 'vue-router'
import { getUser } from '@/stores/user'
import {
  AUTHENTICATED_ACCESS,
  PUBLIC_ACCESS,
  resolveRouteAccess,
  type RouteAccessPolicy
} from '@/services/accessPolicy'
import { routes } from '@/router/routes'

const router = createRouter({ history: createWebHistory('/app/'), routes })

router.beforeEach((to) => {
  const user = getUser()
  if (to.name === 'login' && user?.id) return { name: 'home' }
  const decision = resolveRouteAccess(resolvePolicy(to.meta), user)
  if (decision === 'login') return { name: 'login', query: { redirect: to.fullPath } }
  if (decision === 'forbidden') {
    return { name: 'unauthorized', query: { from: to.fullPath } }
  }
  return true
})

function resolvePolicy(meta: RouteMeta): RouteAccessPolicy {
  if (meta.public) return PUBLIC_ACCESS
  return meta.access || AUTHENTICATED_ACCESS
}

export default router
