import { createApp, type Component } from 'vue'
import App from './App.vue'
import { createPinia } from 'pinia'
import router, { registerProtectedUiPreparation } from './router'

import 'vfonts/Inter.css'
import './styles/main.css'
import { useSessionStore } from '@/features/session/stores/session'
import { registerAuthenticationFailureHandler } from '@/shared/api/http'
import { applyPreferredTheme } from './services/theme'
import { naiveUi } from './plugins/naiveUi'
import { registerSessionScopedStore } from '@/features/session/stores/sessionScope'

const pinia = createPinia()
const app = createApp(App)
const isDevelopmentMode = import.meta.env.DEV
pinia.use(registerSessionScopedStore)
app.use(pinia)
app.use(naiveUi)
let featureUiInstalled = false
let featureUiInstallation: Promise<void> | null = null
registerProtectedUiPreparation(async () => {
  if (featureUiInstalled) return
  if (featureUiInstallation) return featureUiInstallation
  featureUiInstallation = installFeatureUi()
  await featureUiInstallation
})
app.use(router)

async function installFeatureUi(): Promise<void> {
  const { NAIVE_UI_FEATURE_COMPONENTS } = await import('./plugins/naiveUiFeatures')
  for (const component of NAIVE_UI_FEATURE_COMPONENTS) {
    if (!component.name) throw new Error('A feature UI component is missing its registered name.')
    registerFeatureComponent(`N${component.name}`, component)
    const aliases = 'alias' in component && Array.isArray(component.alias) ? component.alias : []
    for (const alias of aliases) registerFeatureComponent(`N${alias}`, component)
  }
  featureUiInstalled = true
}

const session = useSessionStore()
registerAuthenticationFailureHandler(() => {
  const currentRoute = router.currentRoute.value
  session.markAnonymous()
  if (currentRoute.meta.public !== true) {
    void router.replace({ name: 'login', query: { redirect: currentRoute.fullPath } })
  }
})
session.$subscribe((_mutation, state) => applyPreferredTheme(state.user?.preferences))
startStartupPerformanceMeasurements()
applyPreferredTheme(session.getPreferences)
app.mount('#app')

function registerFeatureComponent(name: string, component: Component) {
  if (!app.component(name)) app.component(name, component)
}

function startStartupPerformanceMeasurements() {
  const entries = performance.getEntriesByName('first-contentful-paint')
  if (entries.length > 0) logFirstContentfulPaint(entries[0])
  if (!('PerformanceObserver' in window)) return

  const observer = new PerformanceObserver((list) => {
    const firstContentfulPaint = list.getEntriesByName('first-contentful-paint')[0]
    if (firstContentfulPaint) logFirstContentfulPaint(firstContentfulPaint)
  })
  observer.observe({ type: 'paint', buffered: true })
}

function logFirstContentfulPaint(entry: PerformanceEntry) {
  if (!isDevelopmentMode) return
  console.info(`[performance] first contentful paint: ${entry.startTime.toFixed(2)}ms`)
}
