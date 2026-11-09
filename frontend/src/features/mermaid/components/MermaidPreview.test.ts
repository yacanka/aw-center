// @vitest-environment jsdom
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import { afterEach, describe, expect, it, vi } from 'vitest'
import MermaidPreview from './MermaidPreview.vue'

afterEach(() => vi.useRealTimers())
describe('preview revision fencing', () => {
  it('does not enable export for stale results or messages from another window', async () => {
    vi.useFakeTimers()
    const diagram = {
      id: 'one',
      title: 'One',
      code: 'flowchart LR\n A --> B',
      theme: 'studio' as const
    }
    const wrapper = mount(MermaidPreview, {
      attachTo: document.body,
      props: { diagram, live: true },
      global: {
        stubs: {
          NFlex: { template: '<div><slot/></div>' },
          NText: { template: '<span><slot/></span>' },
          NButton: { template: '<button><slot/></button>' }
        }
      }
    })
    const frame = wrapper.get('iframe').element as HTMLIFrameElement
    const channel = frame.getAttribute('srcdoc')!.match(/data-channel="([^"]+)"/)![1]
    const send = async (data: object, source: Window | null = frame.contentWindow) => {
      window.dispatchEvent(new MessageEvent('message', { source, data: { channel, ...data } }))
      await nextTick()
    }
    const latest = () => wrapper.emitted('status')!.at(-1)![0] as { canExport: boolean }
    await send({ type: 'ready' })
    await send({ type: 'rendered', revision: 1, width: 200, height: 100 })
    expect(latest().canExport).toBe(true)
    await wrapper.setProps({ diagram: { ...diagram, code: 'flowchart LR\n C --> D' } })
    expect(latest().canExport).toBe(false)
    await send({ type: 'rendered', revision: 1, width: 200, height: 100 })
    expect(latest().canExport).toBe(false)
    await send({ type: 'rendered', revision: 2, width: 200, height: 100 }, window)
    expect(latest().canExport).toBe(false)
    await send({ type: 'rendered', revision: 2, width: 200, height: 100 })
    expect(latest().canExport).toBe(true)
    wrapper.unmount()
  })
})
