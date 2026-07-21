import { reactive, type Ref } from 'vue'
import type { DataTableColumn, DataTableColumns, SelectOption } from 'naive-ui'
import type { IColumnSetting, ICompDoc, ICompDocFieldMetadata } from '@/models/compdocs'
import { getDateFilterMenuFunc } from '@/components/table/advancedFilterMenus'
import { getStringFilterMenuFunc } from '@/components/table/valueFilterMenus'
import {
  getArrayFilterFunc,
  getBooleanFilterFunc,
  getDateFilterFunc,
  getStringFilterFunc
} from '@/services/tableFilters'
import {
  clearCompdocColumnSettings,
  createAllColumnSettings,
  createDefaultColumnSettings,
  readCompdocColumnSettings,
  reconcileColumnSettings,
  saveCompdocColumnSettings
} from '@/services/compdocColumns'

type ConfigurableColumn = DataTableColumn<ICompDoc> & Record<string, any>
type FilterHandler = (attribute: string, filterData: unknown) => void

export interface ColumnSettingsState {
  visible: boolean
  list: IColumnSetting[]
}

interface ColumnSettingsDependencies {
  project: Ref<string>
  schemaVersion: Ref<number>
  fields: Ref<ICompDocFieldMetadata[]>
  columnOverrides: Ref<DataTableColumns<ICompDoc>>
  currentColumns: Ref<DataTableColumns<ICompDoc>>
  ordering: Ref<string | null>
  filterValue: Ref<Record<string, unknown>>
  optionSources: () => Record<string, SelectOption[]>
  onFilter: FilterHandler
  onClean: (attribute: string) => void
}

/** Manage schema-safe compliance-document column preferences. */
export function useCompdocColumnSettings(dependencies: ColumnSettingsDependencies) {
  const state = reactive<ColumnSettingsState>({ visible: false, list: [] })
  const load = () => loadSettings(state, dependencies)
  const apply = () => applySettings(state, dependencies)
  return {
    state,
    load,
    apply,
    refresh: () => renderColumns(state, dependencies),
    open: () => (state.visible = true),
    reset: () => resetSettings(state, dependencies),
    useDefault: () => (state.list = createDefaultColumnSettings(dependencies.fields.value)),
    useAll: () => (state.list = createAllColumnSettings(dependencies.fields.value))
  }
}

function loadSettings(state: ColumnSettingsState, dependencies: ColumnSettingsDependencies) {
  state.list = readCompdocColumnSettings(dependencies.project.value, dependencies.fields.value)
}

function applySettings(state: ColumnSettingsState, dependencies: ColumnSettingsDependencies) {
  state.list = reconcileColumnSettings(state.list, dependencies.fields.value)
  renderColumns(state, dependencies)
  saveCompdocColumnSettings(
    dependencies.project.value,
    dependencies.schemaVersion.value,
    state.list
  )
  state.visible = false
}

function renderColumns(state: ColumnSettingsState, dependencies: ColumnSettingsDependencies) {
  const configured = state.list.map((setting) => buildColumn(setting, dependencies))
  dependencies.currentColumns.value = [
    ...fixedColumns(dependencies.columnOverrides.value, 'start'),
    ...configured,
    ...fixedColumns(dependencies.columnOverrides.value, 'end')
  ]
}

function resetSettings(state: ColumnSettingsState, dependencies: ColumnSettingsDependencies) {
  clearCompdocColumnSettings(dependencies.project.value)
  state.list = createDefaultColumnSettings(dependencies.fields.value)
  applySettings(state, dependencies)
}

function buildColumn(setting: IColumnSetting, dependencies: ColumnSettingsDependencies) {
  const metadata = dependencies.fields.value.find((field) => field.key === setting.key)!
  const override = findOverride(setting.key, dependencies.columnOverrides.value)
  return {
    ...override,
    title: metadata.label,
    key: metadata.key,
    width: setting.width,
    sorter: setting.sorter ? 'default' : false,
    sortOrder: resolveSortOrder(metadata.key, dependencies.ordering.value),
    ...filterProperties(setting, metadata, dependencies),
    ellipsis: setting.ellipsis ? { tooltip: true } : false
  } as ConfigurableColumn
}

function filterProperties(
  setting: IColumnSetting,
  metadata: ICompDocFieldMetadata,
  dependencies: ColumnSettingsDependencies
) {
  if (!setting.filter) return { filter: false, renderFilterMenu: undefined }
  const key = metadata.key
  if (metadata.filter_kind === 'date') {
    return {
      filter: getDateFilterFunc(key),
      renderFilterMenu: getDateFilterMenuFunc(key, dependencies.onFilter, dependencies.onClean)
    }
  }
  if (metadata.filter_kind === 'text' || metadata.filter_kind === 'number') {
    return {
      filter: getStringFilterFunc(key),
      filterMultiple: false,
      renderFilterMenu: getStringFilterMenuFunc(
        key,
        dependencies.filterValue,
        dependencies.onFilter
      )
    }
  }
  const booleanFilter = metadata.filter_kind === 'boolean'
  return {
    filter: booleanFilter ? getBooleanFilterFunc(key) : getArrayFilterFunc(key),
    filterMultiple: !booleanFilter,
    filterOptions: resolveOptions(metadata, dependencies)
  }
}

function resolveOptions(metadata: ICompDocFieldMetadata, dependencies: ColumnSettingsDependencies) {
  if (metadata.option_source) return dependencies.optionSources()[metadata.option_source] || []
  if (metadata.filter_kind === 'boolean') {
    return [
      { label: 'Yes', value: true },
      { label: 'No', value: false }
    ]
  }
  return metadata.choices
}

function resolveSortOrder(key: string, ordering: string | null) {
  if (ordering === key) return 'ascend'
  if (ordering === `-${key}`) return 'descend'
  return false
}

function findOverride(key: string, columns: DataTableColumns<ICompDoc>) {
  return columns.find((column) => String((column as ConfigurableColumn).key || '') === key) || {}
}

function fixedColumns(columns: DataTableColumns<ICompDoc>, position: 'start' | 'end') {
  return columns.filter((column) => {
    const configurable = column as ConfigurableColumn
    return position === 'start' ? configurable.type === 'expand' : configurable.key === 'actions'
  })
}
