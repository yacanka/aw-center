import { computed, ref, shallowRef } from 'vue'

interface BeforeInstallPromptEvent extends Event {
  prompt: () => Promise<unknown>
}

interface PwaNavigator {
  standalone?: boolean
  userAgent?: string
}

interface PwaWindow {
  addEventListener?: (type: string, listener: EventListener) => void
  matchMedia?: (query: string) => { matches: boolean }
  removeEventListener?: (type: string, listener: EventListener) => void
}

function matchesStandalone(windowObject?: PwaWindow, navigatorObject?: PwaNavigator): boolean {
  return Boolean(
    navigatorObject?.standalone || windowObject?.matchMedia?.('(display-mode: standalone)').matches
  )
}

function isIosDevice(navigatorObject?: PwaNavigator): boolean {
  return /iphone|ipad|ipod/i.test(navigatorObject?.userAgent || '')
}

export function usePwaInstall({
  windowObject = globalThis.window,
  navigatorObject = globalThis.navigator
}: {
  windowObject?: PwaWindow
  navigatorObject?: PwaNavigator
} = {}) {
  const deferredPrompt = shallowRef<BeforeInstallPromptEvent | null>(null)
  const installed = ref(matchesStandalone(windowObject, navigatorObject))
  const dismissed = ref(false)
  const isInstalling = ref(false)
  const error = ref('')
  const isManualInstall = computed(
    () => isIosDevice(navigatorObject) && !deferredPrompt.value && !installed.value
  )
  const shouldShow = computed(
    () =>
      !installed.value &&
      !dismissed.value &&
      Boolean(deferredPrompt.value || isManualInstall.value || error.value)
  )

  function handleInstallPrompt(event: Event): void {
    if (installed.value) return
    event.preventDefault()
    deferredPrompt.value = event as BeforeInstallPromptEvent
    dismissed.value = false
    error.value = ''
  }

  function handleInstalled(): void {
    installed.value = true
    deferredPrompt.value = null
    error.value = ''
  }

  function start(): void {
    windowObject?.addEventListener?.('beforeinstallprompt', handleInstallPrompt)
    windowObject?.addEventListener?.('appinstalled', handleInstalled)
  }

  function stop(): void {
    windowObject?.removeEventListener?.('beforeinstallprompt', handleInstallPrompt)
    windowObject?.removeEventListener?.('appinstalled', handleInstalled)
  }

  function dismiss(): void {
    dismissed.value = true
    error.value = ''
  }

  async function requestInstall(): Promise<unknown | null> {
    const prompt = deferredPrompt.value
    if (!prompt || isInstalling.value) return null

    isInstalling.value = true
    error.value = ''
    try {
      const result = await prompt.prompt()
      deferredPrompt.value = null
      dismissed.value = true
      return result
    } catch {
      deferredPrompt.value = null
      error.value = 'The installation window could not be opened. Use your browser install menu.'
      return null
    } finally {
      isInstalling.value = false
    }
  }

  return {
    shouldShow,
    isManualInstall,
    isInstalling,
    error,
    start,
    stop,
    dismiss,
    requestInstall
  }
}
