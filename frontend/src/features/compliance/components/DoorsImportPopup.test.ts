// @vitest-environment jsdom
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, h } from 'vue'
import { describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({ source: vi.fn(), preview: vi.fn(), enqueue: vi.fn() }))
vi.mock('@/features/integrations/api/doorsAutomation', () => ({
  enqueueDoorsModuleExport: mocks.enqueue
}))
vi.mock('@/features/compliance/composables/compdocController', () => ({
  useCompdocController: () => ({ fetchCompdocs: vi.fn() })
}))
vi.mock('@/features/compliance/api/compdocImports', () => ({
  fetchDoorsImportSource: mocks.source,
  previewDoorsImport: mocks.preview,
  confirmDoorsImport: vi.fn()
}))
vi.mock('naive-ui', () => ({
  NSelect: defineComponent({
    name: 'NSelect',
    props: ['value', 'options', 'disabled'],
    emits: ['update:value'],
    render() {
      return h(
        'select',
        {
          value: this.value,
          disabled: this.disabled,
          onChange: (event: Event) =>
            this.$emit('update:value', (event.target as HTMLSelectElement).value)
        },
        this.options.map((option: { value: string; label: string; disabled: boolean }) =>
          h('option', { value: option.value, disabled: option.disabled }, option.label)
        )
      )
    }
  })
}))
import DoorsImportPopup from './DoorsImportPopup.vue'

const Slot = { template: '<div><slot /></div>' }
const Table = defineComponent({
  props: ['columns', 'data'],
  setup: (props) => () =>
    h(
      'table',
      props.data.map((row: Record<string, string>) =>
        h(
          'tr',
          props.columns.map((column: { key: string; render?: (value: unknown) => unknown }) =>
            h('td', column.render ? (column.render(row) as string) : row[column.key])
          )
        )
      )
    )
})

describe('DOORS import field linking', () => {
  it('shows actual source coverage, sends exact names, and invalidates a changed preview', async () => {
    mocks.enqueue.mockResolvedValue({ id: 'job-1', status: 'succeeded', progress: 100 })
    mocks.source.mockResolvedValue({
      module_path: '/Project/Module',
      row_count: 2,
      columns: [' Başlık ', 'Other'],
      default_mapping: { ' Başlık ': 'name' },
      target_fields: [
        { key: 'name', label: 'Name', required: true },
        { key: 'notes', label: 'Notes', required: false }
      ],
      column_summaries: {
        ' Başlık ': { populated_count: 1, examples: ['Document title'] },
        Other: { populated_count: 0, examples: [] }
      }
    })
    mocks.preview.mockResolvedValue({
      created_count: 1,
      updated_count: 0,
      unchanged_count: 0,
      rejected_count: 1,
      invalid_documents: [
        {
          row: 2,
          code: 'VALIDATION_ERROR',
          fields: { name: 'Required' },
          doors_object: { absolute_number: 42, identifier: 'REQ-42' }
        }
      ]
    })
    const wrapper = mount(DoorsImportPopup, {
      props: { collectionPath: 'projects/ozgur/compliance-documents/' },
      global: {
        stubs: {
          NModal: Slot,
          NSpace: Slot,
          NAlert: Slot,
          NFormItem: Slot,
          NText: Slot,
          NDivider: Slot,
          NTag: Slot,
          NDataTable: Table,
          NButton: {
            props: ['disabled'],
            template: '<button :disabled="disabled"><slot /></button>'
          },
          NInput: {
            props: ['value'],
            emits: ['update:value'],
            template:
              '<input :value="value" @input="$emit(\'update:value\', $event.target.value)" />'
          }
        }
      }
    })
    try {
      await wrapper.find('input').setValue('/Project/Module')
      await wrapper
        .findAll('button')
        .find((button) => button.text() === 'Load module fields')!
        .trigger('click')
      await flushPromises()
      expect(wrapper.text()).toContain('1 / 2')
      expect(wrapper.text()).toContain('Document title')
      expect(
        wrapper.findAll('select')[1].find('option[value="name"]').attributes('disabled')
      ).toBeDefined()
      await wrapper
        .findAll('button')
        .find((button) => button.text() === 'Validate import')!
        .trigger('click')
      await flushPromises()
      expect(mocks.preview).toHaveBeenCalledWith('projects/ozgur/compliance-documents/', 'job-1', {
        ' Başlık ': 'name'
      })
      expect(wrapper.text()).toContain('REQ-42')
      expect(wrapper.text()).toContain('Confirm import')
      await wrapper.findAll('select')[1].setValue('notes')
      expect(wrapper.text()).not.toContain('Confirm import')
    } finally {
      wrapper.unmount()
    }
  })
})
