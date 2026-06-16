import { createApp } from 'vue'
import App from './App.vue'
import naive from 'naive-ui'
import { createPinia } from 'pinia'
import router from './router'

import './assets/main.css'
import { useUserStore } from './stores/user'
import { bootstrapHttpAuth } from './services/http'

const pinia = createPinia()
const app = createApp(App)
app.use(pinia)
app.use(router)
app.use(naive)

bootstrapHttpAuth()
startStartupPerformanceMeasurements()
applyInitialTheme()
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

  applyInitialTheme()
  await redirectAfterSessionCheck(isLoaded)
  userStore.setSessionInitialized()
  performance.mark('auth-ready-end')
  performance.measure('auth ready', 'auth-ready-start', 'auth-ready-end')
  logPerformanceMeasure('auth ready')
}

async function redirectAfterSessionCheck(isLoaded: boolean) {
  if (!isLoaded && router.currentRoute.value.name !== 'login') {
    await router.push({ name: 'login' })
  }
  if (isLoaded && router.currentRoute.value.name === 'login') {
    await router.push({ name: 'home' })
  }
}

function applyInitialTheme() {
  const systemTheme = window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
  document.documentElement.setAttribute('data-theme', getPreferredTheme(systemTheme))
}

function getPreferredTheme(systemTheme: string) {
  const storedTheme = useUserStore().getPreferences.theme
  return typeof storedTheme === 'string' ? storedTheme : systemTheme
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
  console.info(`[performance] first contentful paint: ${entry.startTime.toFixed(2)}ms`)
}

function logPerformanceMeasure(name: string) {
  const measure = performance.getEntriesByName(name).at(-1)
  if (!measure) return
  console.info(`[performance] ${name}: ${measure.duration.toFixed(2)}ms`)
}
