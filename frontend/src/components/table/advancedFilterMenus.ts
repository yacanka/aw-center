import { h, reactive, type Component } from 'vue'
import {
  NButton,
  NCheckbox,
  NCheckboxGroup,
  NDatePicker,
  NDivider,
  NSelect,
  NSpace
} from 'naive-ui'
import { statusOptions } from '@/services/compdocCatalog'

type FilterHandler = (attribute: string, value: unknown) => void
type CleanHandler = (attribute: string) => void
type FilterMenuActions = { hide: () => void }
type DateFilterState = { filter: boolean; type: string | null; date: string | null }
type ArrayFilterState = { filter: boolean; values: Array<string | number> }

const dateOperatorOptions = ['==', '!=', '>', '>=', '<', '<='].map((value) => ({
  value,
  label: value
}))

/** Build an isolated date-filter menu renderer. */
export function getDateFilterMenuFunc(
  attribute: string,
  onApply: FilterHandler,
  onClean: CleanHandler
) {
  const state = reactive<DateFilterState>({ filter: false, type: null, date: null })
  return (actions: FilterMenuActions) => renderDateMenu(attribute, state, actions, onApply, onClean)
}

/** Build an isolated multi-value status-filter menu renderer. */
export function getArrayFilterMenuFunc(
  attribute: string,
  onApply: FilterHandler,
  onClean: CleanHandler
) {
  const state = reactive<ArrayFilterState>({ filter: false, values: [] })
  return (actions: FilterMenuActions) =>
    renderArrayMenu(attribute, state, actions, onApply, onClean)
}

function renderDateMenu(
  attribute: string,
  state: DateFilterState,
  actions: FilterMenuActions,
  onApply: FilterHandler,
  onClean: CleanHandler
) {
  const apply = () => applyDateFilter(attribute, state, onApply)
  const clean = () => cleanDateFilter(attribute, state, actions, onClean)
  return h(
    NSpace,
    { style: { padding: '8px' } },
    {
      default: () => [dateOperator(state), datePicker(state), toggleButton(state, apply, clean)]
    }
  )
}

function dateOperator(state: DateFilterState) {
  return h(NSelect, {
    options: dateOperatorOptions,
    placeholder: 'Type',
    style: { width: '64px' },
    size: 'tiny',
    value: state.type,
    'onUpdate:value': (value: string) => (state.type = value)
  })
}

function datePicker(state: DateFilterState) {
  return h(NDatePicker as Component, {
    'formatted-value': state.date,
    'onUpdate:formatted-value': (value: string | null) => (state.date = value),
    firstDayOfWeek: 0,
    clearable: false,
    type: 'date',
    size: 'tiny',
    format: 'dd.MM.yyyy',
    style: { width: '96px' }
  })
}

function toggleButton(state: DateFilterState, apply: () => void, clean: () => void) {
  const ready = Boolean(state.date && state.type)
  return h(
    NButton,
    {
      type: state.filter ? 'error' : ready ? 'success' : 'default',
      disabled: !state.filter && !ready,
      onClick: state.filter ? clean : apply,
      size: 'tiny',
      style: { width: '48px' }
    },
    () => (state.filter ? 'Clean' : 'Apply')
  )
}

function renderArrayMenu(
  attribute: string,
  state: ArrayFilterState,
  actions: FilterMenuActions,
  onApply: FilterHandler,
  onClean: CleanHandler
) {
  const apply = () => applyArrayFilter(attribute, state, onApply)
  const clean = () => cleanArrayFilter(attribute, state, actions, onClean)
  return h(
    NSpace,
    { vertical: true, style: { padding: '8px' } },
    {
      default: () => [statusCheckboxes(state), h(NDivider), arrayToggle(state, apply, clean)]
    }
  )
}

function statusCheckboxes(state: ArrayFilterState) {
  return h(
    NCheckboxGroup,
    {
      value: state.values,
      'onUpdate:value': (values: Array<string | number>) => (state.values = values)
    },
    () => h(NSpace, { vertical: true }, () => statusOptions.map(statusCheckbox))
  )
}

function statusCheckbox(option: { value: string; label: string }) {
  return h(NCheckbox, { key: option.value, value: option.value, label: option.label })
}

function arrayToggle(state: ArrayFilterState, apply: () => void, clean: () => void) {
  return h(
    NButton,
    {
      type: state.filter ? 'error' : state.values.length ? 'success' : 'default',
      disabled: !state.filter && !state.values.length,
      onClick: state.filter ? clean : apply,
      size: 'tiny'
    },
    () => (state.filter ? 'Clean' : 'Apply')
  )
}

function applyDateFilter(attribute: string, state: DateFilterState, onApply: FilterHandler): void {
  state.filter = true
  onApply(attribute, { date: state.date, type: state.type })
}

function cleanDateFilter(
  attribute: string,
  state: DateFilterState,
  actions: FilterMenuActions,
  onClean: CleanHandler
): void {
  Object.assign(state, { filter: false, type: null, date: null })
  onClean(attribute)
  actions.hide()
}

function applyArrayFilter(
  attribute: string,
  state: ArrayFilterState,
  onApply: FilterHandler
): void {
  state.filter = true
  onApply(attribute, [...state.values])
}

function cleanArrayFilter(
  attribute: string,
  state: ArrayFilterState,
  actions: FilterMenuActions,
  onClean: CleanHandler
): void {
  Object.assign(state, { filter: false, values: [] })
  onClean(attribute)
  actions.hide()
}
