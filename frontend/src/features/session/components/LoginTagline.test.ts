// @vitest-environment jsdom
import { mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import LoginTagline from './LoginTagline.vue'

describe('login tagline', () => {
  let reduced = false
  let changeMotion: () => void
  const removeListener = vi.fn()
  beforeEach(() => {
    vi.useFakeTimers()
    reduced = false
    vi.stubGlobal('matchMedia', () => ({
      get matches() {
        return reduced
      },
      addEventListener: (_: string, listener: () => void) => {
        changeMotion = listener
      },
      removeEventListener: removeListener
    }))
    vi.spyOn(document, 'hidden', 'get').mockReturnValue(false)
  })
  afterEach(() => {
    vi.useRealTimers()
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })
  it('types, holds, deletes and advances to a different benefit', async () => {
    const wrapper = mount(LoginTagline)
    expect(wrapper.find('button').exists()).toBe(false)
    await vi.advanceTimersByTimeAsync(3200)
    expect(wrapper.get('.tagline-copy').text()).toBe('L')
    await vi.advanceTimersByTimeAsync(45 * 65)
    expect(wrapper.get('.tagline-copy').text()).toBe('Less routine. More room for your expertise.')
    await vi.advanceTimersByTimeAsync(3200 + 42 * 25 + 400 + 65 * 60)
    expect(wrapper.get('.tagline-copy').text()).toBe(
      'Bring your projects, documents and next steps together.'
    )
    wrapper.unmount()
    expect(vi.getTimerCount()).toBe(0)
    expect(removeListener).toHaveBeenCalled()
  })
  it('respects reduced motion, including preference changes', async () => {
    reduced = true
    const wrapper = mount(LoginTagline)
    await wrapper.vm.$nextTick()
    expect(wrapper.get('.tagline-copy').text()).toBe('Less routine. More room for your expertise.')
    expect(wrapper.find('button').exists()).toBe(false)
    expect(vi.getTimerCount()).toBe(0)
    reduced = false
    changeMotion()
    await vi.advanceTimersByTimeAsync(3250)
    reduced = true
    changeMotion()
    await wrapper.vm.$nextTick()
    expect(wrapper.get('.tagline-copy').text()).toBe('Less routine. More room for your expertise.')
    expect(vi.getTimerCount()).toBe(0)
    wrapper.unmount()
  })
})
