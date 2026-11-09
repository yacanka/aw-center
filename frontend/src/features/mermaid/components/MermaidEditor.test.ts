// @vitest-environment jsdom
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import MermaidEditor from './MermaidEditor.vue'

describe('Mermaid code editor', () => {
  it('does not commit partial IME composition and safely highlights markup', async () => {
    const wrapper = mount(MermaidEditor, {
      props: { modelValue: '<img onerror="alert(1)">', diagramId: 'one' },
      global: { stubs: { 'n-flex': true } }
    })
    expect(wrapper.find('img').exists()).toBe(false)
    const input = wrapper.get('textarea')
    await input.trigger('compositionstart')
    ;(input.element as HTMLTextAreaElement).value = '未確定'
    await input.trigger('input')
    expect(wrapper.emitted('update:modelValue')).toBeUndefined()
    await input.trigger('compositionend')
    expect(wrapper.emitted('update:modelValue')?.[0]).toEqual(['未確定'])
  })
})
