import { reactive, type Ref } from 'vue'
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

type ConfigurableColumn = DataTableColumn<ICompDoc> & Record<string, any>

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
  const state = reactive<ColumnSettingsState>({ visible: false, list: [] })

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
  state.list = normalizeColumnSettings(state.list)
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
  state.list = normalizeColumnSettings(state.list)
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
    return normalizeColumnSettings(JSON.parse(rawSettings))
  } catch {
    localStorage.removeItem(COLUMN_SETTINGS_STORAGE_KEY)
    return null
  }
}

function createDefaultSettings(columns: DataTableColumns<ICompDoc>) {
  return columns.map((column) => createColumnSetting(column as ConfigurableColumn))
}

function createColumnSetting(column: ConfigurableColumn): IColumnSetting {
  return {
    key: String(column.key || column.type || ''),
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
  return columns.find((column) => getColumnIdentifier(column as ConfigurableColumn) === key) as
    ConfigurableColumn | undefined
}

function getColumnIdentifier(column: ConfigurableColumn) {
  return String(column.key || column.type || '')
}

function mergeExistingColumn(column: ConfigurableColumn, setting: IColumnSetting) {
  return {
    ...column,
    width: setting.width || column.width,
    sorter: setting.key === DISABLED_ACTION_KEY ? column.sorter : resolveSorter(setting),
    ellipsis: resolveEllipsis(setting, column)
  }
}

function createDynamicColumn(setting: IColumnSetting, dependencies: ColumnSettingsDependencies) {
  const columnKey = setting.key
  return {
    title: setting.title || toTitleCase(columnKey.replaceAll('_', ' ')),
    key: columnKey,
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

function resolveEllipsis(setting: IColumnSetting, column: ConfigurableColumn) {
  if (setting.ellipsis === undefined) return column.ellipsis
  return setting.ellipsis ? { tooltip: true } : false
}

function resolveFilterMenu(setting: IColumnSetting, dependencies: ColumnSettingsDependencies) {
  if (!setting.filter) return null
  if (isDateColumn(setting.key))
    return getDateFilterMenuFunc(setting.key, dependencies.onFilter, dependencies.onClean)
  return getStringFilterMenuFunc(setting.key, dependencies.filterValue, dependencies.onFilter)
}

function resolveFilter(setting: IColumnSetting) {
  if (!setting.filter) return null
  return isDateColumn(setting.key)
    ? getDateFilterFunc(setting.key)
    : getStringFilterFunc(setting.key)
}

function normalizeColumnSettings(settings: unknown): IColumnSetting[] {
  if (!Array.isArray(settings)) return []
  return settings.filter(isValidColumnSetting).map((setting) => ({
    ...setting,
    key: setting.key.trim()
  }))
}

function isValidColumnSetting(setting: unknown): setting is IColumnSetting {
  if (!setting || typeof setting !== 'object') return false
  const key = (setting as Partial<IColumnSetting>).key
  return typeof key === 'string' && key.trim().length > 0
}

function isDateColumn(key: string) {
  return key.includes('date')
}
