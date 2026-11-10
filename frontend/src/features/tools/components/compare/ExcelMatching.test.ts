// @vitest-environment jsdom
import { shallowMount } from '@vue/test-utils'
import { defineComponent } from 'vue'
import { expect, it } from 'vitest'
import ExcelMatching from './ExcelMatching.vue'
import type { ComparisonInspection } from '@/features/tools/api/unifiedComparison'

it('switching worksheets does not silently confirm its automatically suggested header', () => {
  const table = {
    selected: { sheet: 'First', header_row: 1 },
    columns: ['ID'],
    preview: [],
    row_count: 0,
    sheets: [
      { name: 'First', headers: [{ row: 1, labels: ['ID'] }] },
      { name: 'Other', headers: [{ row: 3, labels: ['Content'] }] }
    ]
  }
  const inspection: ComparisonInspection = {
    first: table,
    second: table,
    selection: { first: table.selected, second: table.selected },
    options: { preset: 'balanced', equal_ratio: 0.92, weak_equal_ratio: 0.7, output_type: 'excel' },
    matching: { method: 'content', requires_input: false, keys: [], reason: 'Matched' },
    warnings: []
  }
  const wrapper = shallowMount(ExcelMatching, {
    props: { inspection, selection: inspection.selection, disabled: false },
    global: {
      renderStubDefaultSlot: true,
      stubs: {
        ...Object.fromEntries(
          [
            'n-alert',
            'n-space',
            'n-card',
            'n-form',
            'n-form-item',
            'n-text',
            'n-data-table',
            'n-collapse',
            'n-collapse-item'
          ].map((name) => [name, true])
        ),
        'n-select': defineComponent({
          name: 'SelectStub',
          emits: ['update:value'],
          template: '<div />'
        })
      }
    }
  })
  wrapper.findAllComponents({ name: 'SelectStub' })[0].vm.$emit('update:value', 'Other')
  const selection = wrapper.emitted('update')![0][0] as {
    first: { sheet: string; header_row?: number }
  }
  expect(selection.first.sheet).toBe('Other')
  expect(selection.first.header_row).toBeUndefined()
})
