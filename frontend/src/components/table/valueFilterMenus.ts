import { h, nextTick, ref, type Ref } from 'vue'
import { NInput, NSwitch, type InputInst } from 'naive-ui'
import { toTitleCase } from '@/utils/text'

type FilterValues = Ref<Record<string, unknown>>
type FilterHandler = (attribute: string, value: unknown) => void

/** Build an auto-focused text-filter menu renderer. */
export function getStringFilterMenuFunc(
  attribute: string,
  filterValues: FilterValues,
  onUpdate: FilterHandler
) {
  return () => renderStringFilter(attribute, filterValues, onUpdate)
}

/** Build a boolean-switch filter menu renderer. */
export function getBooleanFilterMenuFunc(
  attribute: string,
  filterValues: FilterValues,
  onUpdate: FilterHandler
) {
  return () =>
    h(NSwitch, {
      value: Boolean(filterValues.value[attribute]),
      size: 'small',
      style: 'margin: 5px; width: 40px',
      'onUpdate:value': (value: boolean) => onUpdate(attribute, value)
    })
}

function renderStringFilter(
  attribute: string,
  filterValues: FilterValues,
  onUpdate: FilterHandler
) {
  const inputReference = ref<InputInst | null>(null)
  void nextTick(() => inputReference.value?.focus())
  return h(NInput, {
    ref: inputReference,
    value: String(filterValues.value[attribute] || ''),
    size: 'small',
    style: 'margin: 5px; width: 180px',
    placeholder: `Filter ${toTitleCase(attribute.replaceAll('_', ' '))}`,
    clearable: true,
    'onUpdate:value': (value: string) => onUpdate(attribute, value || null)
  })
}
