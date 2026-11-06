// @vitest-environment jsdom
import { afterEach, describe, expect, it } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { create } from 'naive-ui'
import { NAIVE_UI_COMPONENTS } from '@/app/plugins/naiveUi'
import { NAIVE_UI_FEATURE_COMPONENTS } from '@/app/plugins/naiveUiFeatures'
import { useReleaseNotesStore } from '@/app/stores/releaseNotes'
import ReleaseNotesModal from './ReleaseNotesModal.vue'

const wrappers: ReturnType<typeof mount>[] = []
afterEach(() => wrappers.splice(0).forEach((wrapper) => wrapper.unmount()))

describe('release note dismissal', () => {
  it.each([true, false])('respects required acknowledgement on Escape (%s)', async (required) => {
    const pinia = createPinia()
    const store = useReleaseNotesStore(pinia)
    store.current = { id: 1, version: '1.0', title: 'Release', requires_ack: required, items: [] }
    store.show = true
    const wrapper = mount(ReleaseNotesModal, {
      attachTo: document.body,
      global: {
        plugins: [
          pinia,
          create({ components: [...NAIVE_UI_COMPONENTS, ...NAIVE_UI_FEATURE_COMPONENTS] })
        ]
      }
    })
    wrappers.push(wrapper)
    await flushPromises()

    document.dispatchEvent(
      new KeyboardEvent('keydown', { key: 'Escape', code: 'Escape', bubbles: true })
    )
    await flushPromises()

    expect(store.show).toBe(required)
  })
})
