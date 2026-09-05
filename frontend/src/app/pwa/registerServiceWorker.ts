const SERVICE_WORKER_URL = '/app/sw.js'
const SERVICE_WORKER_SCOPE = '/app/'

export function registerServiceWorker({
  windowObject = globalThis.window,
  navigatorObject = globalThis.navigator
}: {
  windowObject?: Window
  navigatorObject?: Navigator
} = {}): void {
  if (!import.meta.env.PROD || !navigatorObject?.serviceWorker) return

  windowObject.addEventListener(
    'load',
    () => {
      navigatorObject.serviceWorker
        .register(SERVICE_WORKER_URL, { scope: SERVICE_WORKER_SCOPE })
        .catch((error: unknown) => {
          console.error('PWA service worker registration failed.', error)
        })
    },
    { once: true }
  )
}
