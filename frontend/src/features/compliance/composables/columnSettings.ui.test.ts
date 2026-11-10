// @vitest-environment jsdom
import { mount } from '@vue/test-utils'
import { defineComponent, h, ref } from 'vue'
import { NConfigProvider, NDataTable, darkTheme } from 'naive-ui'
import { expect, it } from 'vitest'
import type { DataTableColumns } from 'naive-ui'
import type { ICompDoc, ICompDocFieldMetadata } from '../models/compdocs'
import { useCompdocColumnSettings } from './columnSettings'

for (const theme of [null, darkTheme]) {
  it(`highlights active text and select filters and preserves independent state in ${theme ? 'dark' : 'light'} theme`, async () => {
    const filters = ref<Record<string, unknown>>({})
    const columns = ref<DataTableColumns<ICompDoc>>([])
    const fields = ['name', 'panel', 'ata'].map((key) => ({
      key,
      label: key,
      type: 'CharField',
      required: false,
      read_only: false,
      width: 160,
      default_visible: true,
      sortable: true,
      ellipsis: false,
      filter_kind: key === 'name' ? 'text' : 'select',
      choices: [],
      option_source: key === 'panel' ? 'panels' : key === 'ata' ? 'atas' : null
    })) as ICompDocFieldMetadata[]
    const wrapper = mount(
      defineComponent({
        setup() {
          const settings = useCompdocColumnSettings({
            project: ref('filter-test'),
            schemaVersion: ref(4),
            fields: ref(fields),
            columnOverrides: ref([]),
            currentColumns: columns,
            ordering: ref(null),
            filterValue: filters,
            optionSources: () => ({
              panels: [{ label: 'Systems', value: 1 }],
              atas: [{ label: '27-00', value: '27-00' }]
            }),
            onFilter: (key, value) => {
              filters.value[key] = value
            },
            onClean: (key) => {
              delete filters.value[key]
            }
          })
          settings.load()
          settings.apply()
          return () =>
            h(
              NConfigProvider,
              { theme },
              { default: () => h(NDataTable, { columns: columns.value, data: [], remote: true }) }
            )
        }
      })
    )
    try {
      expect(wrapper.findAll('.compdoc-filter-icon--active')).toHaveLength(0)
      filters.value.name = 'flight'
      filters.value.ata = ['27-00']
      await wrapper.vm.$nextTick()
      expect(wrapper.findAll('.compdoc-filter-icon--active')).toHaveLength(2)
      expect(wrapper.find('[aria-label="Filter panel"]').classes()).not.toContain(
        'compdoc-filter-icon--active'
      )
      expect(wrapper.find('[aria-label="Filter ata"]').attributes('style')).toContain(
        'var(--n-th-icon-color-active)'
      )
      delete filters.value.ata
      await wrapper.vm.$nextTick()
      expect(wrapper.findAll('.compdoc-filter-icon--active')).toHaveLength(1)
      expect(filters.value.name).toBe('flight')
    } finally {
      wrapper.unmount()
    }
  })
}
