import { createApp } from 'vue'
import App from './App.vue'
import naive from 'naive-ui'
import { createPinia } from 'pinia'
import router from './router'

import './assets/main.css'
import { useUserStore } from './stores/user'
import { bootstrapHttpAuth } from './services/http'
import { applyPreferredTheme } from './services/theme'

const pinia = createPinia()
const app = createApp(App)
const isDevelopmentMode = import.meta.env.DEV
app.use(pinia)
app.use(router)
app.use(naive)

bootstrapHttpAuth()
startStartupPerformanceMeasurements()
applyPreferredTheme(useUserStore().getPreferences)
app.mount('#app')
initializeSession()

/**
 * Boots the authenticated browser session after the UI is mounted.
 */
export async function initializeSession() {
  performance.mark('auth-ready-start')
  const userStore = useUserStore()
  const isLoaded = await userStore.fetchCurrentUser({
    allowCachedFallback: true,
    suppressAuthenticationWarning: true
  })

  applyPreferredTheme(userStore.getPreferences)
  await redirectAfterSessionCheck(isLoaded)
  userStore.setSessionInitialized()
  performance.mark('auth-ready-end')
  performance.measure('auth ready', 'auth-ready-start', 'auth-ready-end')
  logPerformanceMeasure('auth ready')
}

async function redirectAfterSessionCheck(isLoaded: boolean) {
  const isPublicPage = router.currentRoute.value.meta.public === true
  if (!isLoaded && !isPublicPage) {
    await router.push({ name: 'login' })
  }
  if (isLoaded && router.currentRoute.value.name === 'login') {
    await router.push({ name: 'home' })
  }
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

function logPerformanceMeasure(name: string) {
  if (!isDevelopmentMode) return
  const measure = performance.getEntriesByName(name).at(-1)
  if (!measure) return
  console.info(`[performance] ${name}: ${measure.duration.toFixed(2)}ms`)
}
