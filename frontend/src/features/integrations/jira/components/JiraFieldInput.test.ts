// @vitest-environment jsdom
import { mount } from '@vue/test-utils'
import { defineComponent } from 'vue'
import { describe, expect, it } from 'vitest'
import type { IJiraField, JiraFieldValue } from '@/features/integrations/jira/models/jira'
import JiraFieldInput from './JiraFieldInput.vue'

const DatePicker = defineComponent({
  props: ['formattedValue', 'format', 'valueFormat', 'type'],
  emits: ['update:formatted-value'],
  template: '<div />'
})

const Select = defineComponent({
  props: ['value', 'options'],
  emits: ['update:value'],
  template: '<div />'
})
function editor(modelValue: JiraFieldValue, field: Partial<IJiraField>) {
  return mount(JiraFieldInput, {
    props: { modelValue, field: { id: 'customfield_123', name: 'Review', ...field } },
    global: {
      stubs: {
        NSelect: Select,
        NDatePicker: DatePicker,
        NFlex: { template: '<div><slot /></div>' }
      }
    }
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

it('displays date fields in Turkish while preserving the ISO calendar wire value', () => {
  const wrapper = editor('2026-10-13', { schema: { type: 'date' } })
  const picker = wrapper.findComponent(DatePicker)
  expect(picker.props('format')).toBe('dd.MM.yyyy')
  expect(picker.props('formattedValue')).toBe('2026-10-13')
  picker.vm.$emit('update:formatted-value', '2026-10-14')
  expect(wrapper.emitted('update:modelValue')?.[0]).toEqual(['2026-10-14'])
})

it('displays datetime fields in Istanbul and submits the selected time with UTC+3', () => {
  const wrapper = editor('2026-10-13T22:05:06Z', { schema: { type: 'datetime' } })
  const picker = wrapper.findComponent(DatePicker)
  expect(picker.props('formattedValue')).toBe('14.10.2026 01:05:06')
  picker.vm.$emit('update:formatted-value', '15.10.2026 16:30:00')
  expect(wrapper.emitted('update:modelValue')?.[0]).toEqual(['2026-10-15T16:30:00+03:00'])
})
