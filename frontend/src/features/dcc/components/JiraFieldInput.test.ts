// @vitest-environment jsdom
import { mount } from '@vue/test-utils'
import { defineComponent } from 'vue'
import { describe, expect, it } from 'vitest'
import type { IJiraField, JiraFieldValue } from '@/features/dcc/models/jira'
import JiraFieldInput from './JiraFieldInput.vue'

const Select = defineComponent({
  props: ['value', 'options'],
  emits: ['update:value'],
  template: '<div />'
})
function editor(modelValue: JiraFieldValue, field: Partial<IJiraField>) {
  return mount(JiraFieldInput, {
    props: { modelValue, field: { id: 'customfield_123', name: 'Review', ...field } },
    global: { stubs: { NSelect: Select, NFlex: { template: '<div><slot /></div>' } } }
  })
}

describe('JIRA field editor', () => {
  it('uses stable IDs for both saved labels and object values', () => {
    for (const value of ['Review', { id: '12', value: 'Review' }]) {
      const wrapper = editor(value, {
        schema: { type: 'option' },
        allowedValues: [{ id: '12', value: 'Review', label: 'Review' }]
      })
      expect(wrapper.findComponent(Select).props('value')).toBe('12')
    }
  })

  it('resets the child when the parent selection changes', () => {
    const wrapper = editor(
      { id: '12', child: { id: '13' } },
      {
        schema: { type: 'option', custom: 'jira:cascadingselect' },
        allowedValues: [{ id: '12', value: 'Parent', children: [{ id: '13', value: 'Child' }] }]
      }
    )
    expect(wrapper.findAllComponents(Select)[1].props('value')).toBe('13')
    wrapper.findAllComponents(Select)[0].vm.$emit('update:value', '20')
    expect(wrapper.emitted('update:modelValue')?.[0]).toEqual([{ id: '20' }])
  })

  it('preserves false as a value', () => {
    const wrapper = editor(false, { schema: { type: 'boolean' } })
    expect(wrapper.findComponent(Select).props('value')).toBe('false')
    wrapper.findComponent(Select).vm.$emit('update:value', 'false')
    expect(wrapper.emitted('update:modelValue')?.[0]).toEqual([false])
  })
})
