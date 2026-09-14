// @vitest-environment jsdom
import { mount } from '@vue/test-utils'
import { reactive, nextTick } from 'vue'
import { afterEach, expect, it, vi } from 'vitest'
import Welcome from './Welcome.vue'

const mocks = vi.hoisted(() => ({
  session: { getPreferences: { theme: 'light' } },
  push: vi.fn()
}))
vi.mock('@/features/session/stores/session', () => ({ useSessionStore: () => mocks.session }))
vi.mock('vue-router', () => ({ useRouter: () => ({ push: mocks.push }) }))

afterEach(() => vi.useRealTimers())

it('uses opposite particle colors reactively, has no video, and still redirects after eight seconds', async () => {
  vi.useFakeTimers()
  mocks.session = reactive({ getPreferences: { theme: 'light' } })
  const stopAnimation = vi.fn()
  const wrapper = mount(Welcome, {
    global: {
      stubs: {
        ParticleText: {
          name: 'ParticleTextAnimator',
          props: ['text', 'colors'],
          methods: { stopAnimation },
          template: '<canvas />'
        }
      }
    }
  })
  const particles = wrapper.findComponent({ name: 'ParticleTextAnimator' })
  expect(wrapper.find('video').exists()).toBe(false)
  expect(particles.props('colors')).toEqual(['#00000088'])
  mocks.session.getPreferences.theme = 'dark'
  await nextTick()
  expect(particles.props('colors')).toEqual(['#ffffff88'])
  vi.advanceTimersByTime(8000)
  expect(stopAnimation).toHaveBeenCalledOnce()
  expect(mocks.push).toHaveBeenCalledWith({ name: 'login' })
  wrapper.unmount()
})
