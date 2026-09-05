import { describe, expect, it, vi } from 'vitest'

import { usePwaInstall } from './usePwaInstall'

class FakeWindow extends EventTarget {
  constructor(private readonly standalone = false) {
    super()
  }

  matchMedia() {
    return { matches: this.standalone }
  }
}

function installPromptEvent(prompt = vi.fn(async () => ({ outcome: 'accepted' }))) {
  const event = new Event('beforeinstallprompt', { cancelable: true }) as Event & {
    prompt: typeof prompt
  }
  event.prompt = prompt
  return event
}

describe('PWA install flow', () => {
  it('reveals the install option and invokes the retained browser prompt once', async () => {
    const windowObject = new FakeWindow()
    const install = usePwaInstall({ windowObject, navigatorObject: { userAgent: 'Chrome' } })
    const prompt = vi.fn(async () => ({ outcome: 'accepted' }))
    const event = installPromptEvent(prompt)

    install.start()
    windowObject.dispatchEvent(event)

    expect(event.defaultPrevented).toBe(true)
    expect(install.shouldShow.value).toBe(true)
    await expect(install.requestInstall()).resolves.toEqual({ outcome: 'accepted' })
    expect(prompt).toHaveBeenCalledOnce()
    expect(install.shouldShow.value).toBe(false)
    install.stop()
  })

  it('hides the option when the app is installed or already standalone', () => {
    const standaloneWindow = new FakeWindow(true)
    const standalone = usePwaInstall({
      windowObject: standaloneWindow,
      navigatorObject: { userAgent: 'Chrome' }
    })
    standalone.start()
    standaloneWindow.dispatchEvent(installPromptEvent())
    expect(standalone.shouldShow.value).toBe(false)

    const windowObject = new FakeWindow()
    const install = usePwaInstall({ windowObject, navigatorObject: { userAgent: 'Chrome' } })
    install.start()
    windowObject.dispatchEvent(installPromptEvent())
    windowObject.dispatchEvent(new Event('appinstalled'))
    expect(install.shouldShow.value).toBe(false)
  })

  it('offers manual installation guidance on iOS and supports dismissal', () => {
    const install = usePwaInstall({
      windowObject: new FakeWindow(),
      navigatorObject: { userAgent: 'Mozilla/5.0 (iPhone) Safari' }
    })

    expect(install.isManualInstall.value).toBe(true)
    expect(install.shouldShow.value).toBe(true)
    install.dismiss()
    expect(install.shouldShow.value).toBe(false)
  })

  it('keeps an actionable error visible when the browser prompt fails', async () => {
    const windowObject = new FakeWindow()
    const install = usePwaInstall({ windowObject, navigatorObject: { userAgent: 'Chrome' } })
    install.start()
    windowObject.dispatchEvent(
      installPromptEvent(vi.fn(async () => Promise.reject(new Error('prompt failed'))))
    )

    await install.requestInstall()

    expect(install.error.value).toContain('installation window could not be opened')
    expect(install.shouldShow.value).toBe(true)
  })
})
