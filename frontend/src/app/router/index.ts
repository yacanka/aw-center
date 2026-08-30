import { createRouter, createWebHistory } from 'vue-router'
import { useSessionStore } from '@/features/session/stores/session'
import { routes } from '@/app/router/routes'
import { resolveSessionRoute } from '@/features/session/services/sessionRouteGuard'
import { captureInitialPasswordResetCapability } from '@/features/session/services/passwordResetCapability'

captureInitialPasswordResetCapability()

const router = createRouter({ history: createWebHistory('/app/'), routes })

let prepareProtectedUi: () => Promise<void> = async () => {}

router.beforeEach(async (to) => {
  if (to.meta.public !== true) await prepareProtectedUi()
  return resolveSessionRoute(to, useSessionStore())
})

/** Install the lazy feature component graph before session bootstrap can mount the protected shell. */
export function registerProtectedUiPreparation(handler: () => Promise<void>): void {
  prepareProtectedUi = handler
}

export default router
