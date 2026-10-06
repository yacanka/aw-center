// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createApp, defineComponent, nextTick } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'
import { naiveUi } from '@/app/plugins/naiveUi'
import { registerSessionScopedStore } from '@/features/session/stores/sessionScope'

vi.mock('@/features/assistant/api/assistant', async (importOriginal) => ({
  ...(await importOriginal<object>()),
  fetchAssistantCatalog: vi.fn(),
  sendAssistantMessage: vi.fn()
}))
import * as api from '@/features/assistant/api/assistant'
import { useAssistantStore } from '@/features/assistant/stores/assistant'
import AssistantPanel from './AssistantPanel.vue'

const card = {
  id: 'compare',
  title: 'Compare',
  path: '/compare',
  description: 'Compare documents.'
}
const reply = {
  answer: '<img src=x onerror=alert(1)> [external](https://example.com)',
  applications: [card, { ...card, id: 'unsafe', path: 'https://example.com', title: 'Unsafe' }],
  sources: [{ id: 'guide', title: 'Compare guide', path: '/compare' }]
}
const wrappers: VueWrapper[] = []

async function panel() {
  const pinia = createPinia()
  pinia.use(registerSessionScopedStore)
  createApp({}).use(pinia)
  setActivePinia(pinia)
  const router = createRouter({
    history: createMemoryHistory('/app/'),
    routes: ['/home', '/compare'].map((path) => ({
      path,
      component: defineComponent({ template: '<div />' })
    }))
  })
  await router.push('/home?filter=private#fragment')
  await router.isReady()
  const wrapper = mount(AssistantPanel, {
    attachTo: document.body,
    props: { show: true },
    global: { plugins: [pinia, router, naiveUi], stubs: { transition: false } }
  })
  wrappers.push(wrapper)
  await flushPromises()
  return { wrapper, router, store: useAssistantStore(pinia) }
}
function button(label: string) {
  const match = Array.from(document.querySelectorAll<HTMLButtonElement>('button')).find(
    (el) => el.textContent?.trim() === label || el.getAttribute('aria-label') === label
  )
  if (!match) throw new Error(`Missing button: ${label}`)
  return match
}
async function typeMessage(value: string) {
  const textarea = document.querySelector<HTMLTextAreaElement>('textarea')!
  textarea.value = value
  textarea.dispatchEvent(new Event('input', { bubbles: true }))
  await nextTick()
  return textarea
}

describe('assistant panel interactions', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(api.fetchAssistantCatalog).mockResolvedValue({
      status: 'configured',
      applications: [card]
    })
    vi.mocked(api.sendAssistantMessage).mockResolvedValue(reply)
  })
  afterEach(() => {
    wrappers.splice(0).forEach((wrapper) => wrapper.unmount())
    document.body.innerHTML = ''
  })

  it('discloses AI service use and renders answers as literal text with only resolved cards', async () => {
    const { store, router } = await panel()
    expect(document.body.textContent).toContain('Messages are sent to the configured AI service.')
    await store.send('Help', '/home')
    await flushPromises()
    expect(document.body.textContent).toContain(reply.answer)
    expect(document.querySelector('img')).toBeNull()
    expect(document.querySelector('a[href^="https:"]')).toBeNull()
    expect(document.body.textContent).not.toContain('Unsafe')
    expect(document.body.textContent).toContain(
      'Application guides are references, not a guarantee of answer accuracy.'
    )
    expect(router.currentRoute.value.path).toBe('/home')
    button('Open Compare').click()
    await flushPromises()
    expect(router.currentRoute.value.path).toBe('/compare')
  })

  it('sends Enter with only route.path and preserves Shift+Enter and IME composition', async () => {
    await panel()
    const textarea = await typeMessage('First\nSecond')
    expect(textarea.id).toBe('assistant-message')
    expect(textarea.getAttribute('aria-label')).toBe('Message to assistant')
    const shifted = new KeyboardEvent('keydown', {
      key: 'Enter',
      shiftKey: true,
      bubbles: true,
      cancelable: true
    })
    textarea.dispatchEvent(shifted)
    expect(shifted.defaultPrevented).toBe(false)
    textarea.dispatchEvent(
      new KeyboardEvent('keydown', {
        key: 'Enter',
        isComposing: true,
        bubbles: true,
        cancelable: true
      })
    )
    expect(api.sendAssistantMessage).not.toHaveBeenCalled()
    textarea.dispatchEvent(
      new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true })
    )
    await flushPromises()
    expect(api.sendAssistantMessage).toHaveBeenCalledWith(
      { message: 'First\nSecond', history: [], current_path: '/home' },
      expect.any(AbortSignal)
    )
    expect(textarea.value).toBe('')
  })

  it('keeps conversation on close/reopen, resets on New chat, and returns focus to the trigger', async () => {
    const trigger = document.createElement('button')
    trigger.textContent = 'Assistant trigger'
    document.body.append(trigger)
    trigger.focus()
    const { wrapper, store } = await panel()
    await store.send('Hello', '/home')
    await flushPromises()
    button('Close assistant').click()
    expect(wrapper.emitted('update:show')?.at(-1)).toEqual([false])
    await wrapper.setProps({ show: false })
    await flushPromises()
    await vi.waitFor(() => expect(document.activeElement).toBe(trigger))
    await wrapper.setProps({ show: true })
    await flushPromises()
    expect(store.messages).toHaveLength(2)
    button('New chat').click()
    await flushPromises()
    expect(store.messages).toEqual([])
    await vi.waitFor(() => expect(document.activeElement?.tagName).toBe('TEXTAREA'))
  })

  it.each(['unconfigured', 'invalid'] as const)(
    'shows authorized fallback applications when %s',
    async (status) => {
      vi.mocked(api.fetchAssistantCatalog).mockResolvedValue({ status, applications: [card] })
      const { router } = await panel()
      expect(document.body.textContent).toContain(
        status === 'unconfigured'
          ? 'AI service is not configured.'
          : 'AI service configuration needs attention.'
      )
      expect(document.querySelector<HTMLTextAreaElement>('textarea')?.disabled).toBe(true)
      expect(document.querySelector('article[aria-label="Available applications"]')).not.toBeNull()
      expect(document.querySelector('article[aria-label="Assistant response"]')).toBeNull()
      expect(document.activeElement).toBe(button('Close assistant'))
      button('Open Compare').click()
      await flushPromises()
      expect(router.currentRoute.value.path).toBe('/compare')
    }
  )

  it('shows shared errors and 429 guidance and retries without another user turn', async () => {
    vi.mocked(api.sendAssistantMessage).mockRejectedValueOnce({
      response: {
        data: { code: 'THROTTLED', detail: 'Too many requests.', request_id: 'request-1' }
      }
    })
    const { store } = await panel()
    await typeMessage('Help')
    button('Send').click()
    await flushPromises()
    expect(document.body.textContent).toContain('Too many requests.')
    expect(document.body.textContent).toContain('Wait a minute before trying again.')
    expect(document.body.textContent).toContain('request-1')
    button('Try again').click()
    await flushPromises()
    expect(store.messages.filter((row) => row.role === 'user')).toHaveLength(1)
  })

  it('provides an explicit catalog retry without sending a chat on catalog failure', async () => {
    vi.mocked(api.fetchAssistantCatalog).mockRejectedValueOnce(new Error('Catalog unavailable.'))
    const { store } = await panel()
    expect(document.body.textContent).toContain('Catalog unavailable.')
    button('Reload applications').click()
    await flushPromises()
    expect(store.catalog?.status).toBe('configured')
    expect(api.sendAssistantMessage).not.toHaveBeenCalled()
  })

  it('names the drawer for assistive technology and closes with Escape', async () => {
    const { wrapper } = await panel()
    expect(document.querySelector('[role="dialog"]')?.getAttribute('aria-label')).toBe(
      'AW Center Assistant'
    )
    document.dispatchEvent(
      new KeyboardEvent('keydown', { key: 'Escape', code: 'Escape', bubbles: true })
    )
    await nextTick()
    expect(wrapper.emitted('update:show')?.at(-1)).toEqual([false])
  })

  it('disables sending over-limit Unicode input without truncating the draft', async () => {
    await panel()
    const draft = '😀'.repeat(4001)
    const textarea = await typeMessage(draft)
    expect(button('Send').disabled).toBe(true)
    expect(textarea.value).toBe(draft)
    expect(document.body.textContent).toContain('4,001 / 4,000')
    expect(api.sendAssistantMessage).not.toHaveBeenCalled()
  })
})
