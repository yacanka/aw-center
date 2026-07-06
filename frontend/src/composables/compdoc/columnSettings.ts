import type { Ref } from 'vue'
import type { DataTableColumn, DataTableColumns, SelectOption } from 'naive-ui'
import type { IColumnSetting, ICompDoc } from '@/models/compdocs'
import { toTitleCase } from '@/utils/text'
import {
  getDateFilterFunc,
  getDateFilterMenuFunc,
  getStringFilterFunc,
  getStringFilterMenuFunc
} from '@/stores/datatable'

const COLUMN_SETTINGS_STORAGE_KEY = 'compdocs>column_settings'
const DISABLED_ACTION_KEY = 'actions'

type FilterValue = Ref<Record<string, unknown>>
type FilterHandler = (attribute: string, filterData: unknown) => void
type CleanHandler = (attribute: string) => void

export interface ColumnSettingsState {
  visible: boolean
  list: IColumnSetting[]
}

interface ColumnSettingsDependencies {
  allColumns: Ref<DataTableColumns<ICompDoc>>
  currentColumns: Ref<DataTableColumns<ICompDoc>>
  columnSelections: SelectOption[]
  filterValue: FilterValue
  onFilter: FilterHandler
  onClean: CleanHandler
}

/** Manage persisted compliance document table column preferences. */
export function useCompdocColumnSettings(dependencies: ColumnSettingsDependencies) {
  const state: ColumnSettingsState = { visible: false, list: [] }

  return {
    state,
    apply: () => applyColumnSettings(state, dependencies),
    reset: () => resetColumnSettings(state, dependencies),
    load: () => loadColumnSettings(state, dependencies.allColumns.value),
    open: () => openColumnSettings(state, dependencies.columnSelections),
    handleFieldChange: () => lockSelectedOptions(state, dependencies.columnSelections)
  }
}

function applyColumnSettings(state: ColumnSettingsState, dependencies: ColumnSettingsDependencies) {
  dependencies.currentColumns.value = state.list
    .map((setting) => buildColumn(setting, dependencies))
    .filter(Boolean) as DataTableColumns<ICompDoc>
  localStorage.setItem(COLUMN_SETTINGS_STORAGE_KEY, JSON.stringify(state.list))
}

function resetColumnSettings(state: ColumnSettingsState, dependencies: ColumnSettingsDependencies) {
  localStorage.removeItem(COLUMN_SETTINGS_STORAGE_KEY)
  loadColumnSettings(state, dependencies.allColumns.value)
  applyColumnSettings(state, dependencies)
}

function openColumnSettings(state: ColumnSettingsState, columnSelections: SelectOption[]) {
  lockSelectedOptions(state, columnSelections)
  state.visible = true
}

function lockSelectedOptions(state: ColumnSettingsState, columnSelections: SelectOption[]) {
  const selectedKeys = new Set(state.list.map((item) => item.key))
  columnSelections.forEach((option) => {
    option.disabled = selectedKeys.has(option.value as string)
  })
}

function loadColumnSettings(state: ColumnSettingsState, columns: DataTableColumns<ICompDoc>) {
  const savedSettings = readSavedSettings()
  state.list = savedSettings || createDefaultSettings(columns)
}

function readSavedSettings() {
  const rawSettings = localStorage.getItem(COLUMN_SETTINGS_STORAGE_KEY)
  if (!rawSettings) return null

  try {
    return JSON.parse(rawSettings) as IColumnSetting[]
  } catch {
    localStorage.removeItem(COLUMN_SETTINGS_STORAGE_KEY)
    return null
  }
}

function createDefaultSettings(columns: DataTableColumns<ICompDoc>) {
  return columns.map((column) => createColumnSetting(column as DataTableColumn<ICompDoc>))
}

function createColumnSetting(column: DataTableColumn<ICompDoc>) {
  return {
    key: String(column.key || ''),
    title: String(column.title || ''),
    width: column.width,
    sorter: Boolean(column.sorter),
    filter: Boolean(column.filter),
    ellipsis: Boolean(column.ellipsis)
  }
}

function buildColumn(setting: IColumnSetting, dependencies: ColumnSettingsDependencies) {
  const existingColumn = findExistingColumn(setting.key, dependencies.allColumns.value)
  return existingColumn
    ? mergeExistingColumn(existingColumn, setting)
    : createDynamicColumn(setting, dependencies)
}

function findExistingColumn(key: string, columns: DataTableColumns<ICompDoc>) {
  return columns.find((column) => String((column as DataTableColumn<ICompDoc>).key) === key)
}

function mergeExistingColumn(column: DataTableColumn<ICompDoc>, setting: IColumnSetting) {
  return {
    ...column,
    width: setting.width || column.width,
    sorter: setting.key === DISABLED_ACTION_KEY ? column.sorter : resolveSorter(setting),
    ellipsis: resolveEllipsis(setting, column)
  }
}

function createDynamicColumn(setting: IColumnSetting, dependencies: ColumnSettingsDependencies) {
  return {
    title: setting.title || toTitleCase(setting.key.replaceAll('_', ' ')),
    key: setting.key,
    sorter: resolveSorter(setting),
    width: setting.width || 12,
    renderFilterMenu: resolveFilterMenu(setting, dependencies),
    filter: resolveFilter(setting),
    ellipsis: setting.ellipsis ? { tooltip: true } : null
  }
}

function resolveSorter(setting: IColumnSetting) {
  return setting.sorter ? 'default' : false
}

function resolveEllipsis(setting: IColumnSetting, column: DataTableColumn<ICompDoc>) {
  if (setting.ellipsis === undefined) return column.ellipsis
  return setting.ellipsis ? { tooltip: true } : false
}

function resolveFilterMenu(setting: IColumnSetting, dependencies: ColumnSettingsDependencies) {
  if (!setting.filter) return null
  if (setting.key.includes('date'))
    return getDateFilterMenuFunc(setting.key, dependencies.onFilter, dependencies.onClean)
  return getStringFilterMenuFunc(setting.key, dependencies.filterValue, dependencies.onFilter)
}

function resolveFilter(setting: IColumnSetting) {
  if (!setting.filter) return null
  return setting.key.includes('date')
    ? getDateFilterFunc(setting.key)
    : getStringFilterFunc(setting.key)
}
