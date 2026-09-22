<template>
  <n-text v-if="inputType === 'unsupported'" type="error">
    Unsupported JIRA field type. Update the JIRA create screen before submitting.
  </n-text>
  <n-flex v-else-if="isCascade" vertical>
    <n-select
      :value="cascadeParent"
      :options="allowedOptions"
      filterable
      clearable
      :placeholder="field.name"
      @update:value="updateParent"
    />
    <n-select
      v-if="childOptions.length"
      :value="cascadeChild"
      :options="childOptions"
      filterable
      clearable
      placeholder="Child option"
      @update:value="updateChild"
    />
  </n-flex>
  <n-select
    v-else-if="allowedOptions.length"
    :value="modelValueAsSelect"
    :options="allowedOptions"
    :multiple="isMultiple"
    filterable
    clearable
    :placeholder="field.name"
    @update:value="updateValue"
  />
  <n-dynamic-tags
    v-else-if="isMultiple"
    :value="modelValueAsArray"
    @update:value="updateArrayValue"
  />
  <n-select
    v-else-if="inputType === 'boolean'"
    :value="
      modelValue === true ? 'true' : modelValue === false ? 'false' : modelValueAsString || null
    "
    :options="[
      { label: 'True', value: 'true' },
      { label: 'False', value: 'false' }
    ]"
    clearable
    :placeholder="field.name"
    @update:value="updateBoolean"
  />
  <n-input
    v-else-if="inputType === 'datetime'"
    :value="modelValueAsString"
    placeholder="YYYY-MM-DDTHH:mm:ss+03:00"
    @update:value="updateValue"
  />
  <n-search
    v-else-if="inputType == 'person'"
    :value="modelValueAsString"
    :placeholder="field.name"
    @update:value="updateValue"
    @change="emitChange"
  />
  <n-date-picker
    v-else-if="inputType == 'date'"
    :formatted-value="modelValueAsDate"
    value-format="yyyy-MM-dd"
    type="date"
    clearable
    style="width: 100%"
    :placeholder="field.name"
    @update:formatted-value="updateDateValue"
  />
  <n-input-number
    v-else-if="inputType == 'number'"
    :value="modelValueAsNumber"
    clearable
    style="width: 100%"
    :placeholder="field.name"
    @update:value="updateValue"
  />
  <n-input
    v-else
    :value="modelValueAsString"
    :placeholder="field.name"
    @update:value="updateValue"
    @change="emitChange"
  />
</template>

<script setup lang="ts">
import { computed } from 'vue'
import NSearch from '@/shared/components/NSearch.vue'
import { IJiraField, JiraFieldValue } from '@/features/dcc/models/jira'
import { jiraInputToken, resolveJiraFieldInputType } from '@/shared/utils/jiraFieldInput'

const props = defineProps<{
  field: IJiraField
  modelValue?: JiraFieldValue
}>()

const emits = defineEmits<{
  'update:modelValue': [value: JiraFieldValue]
  change: []
}>()

const inputType = computed(() => resolveJiraFieldInputType(props.field))
const isMultiple = computed(() => String(props.field.schema?.type || '') == 'array')
function selectOptions(options: Array<Record<string, unknown>>) {
  return options.flatMap((option) => {
    const value = jiraInputToken(option.id ?? option.value ?? option)
    return value === null
      ? []
      : [{ value, label: String(option.label ?? option.value ?? option.name ?? value) }]
  })
}
const allowedOptions = computed(() => selectOptions(props.field.allowedValues || []))
const isCascade = computed(
  () =>
    props.field.schema?.type === 'option-with-child' ||
    String(props.field.schema?.custom || '').endsWith(':cascadingselect')
)
const cascadeParent = computed(() => selectionToken(props.modelValue))
const parentOption = computed(() =>
  (props.field.allowedValues || []).find((option) =>
    [option.id, option.value].some(
      (value) => value != null && String(value) === String(cascadeParent.value)
    )
  )
)
const childOptions = computed(() =>
  selectOptions((parentOption.value?.children || []) as Array<Record<string, unknown>>)
)
const cascadeChild = computed(() => {
  const value = props.modelValue
  return value && typeof value === 'object' && !Array.isArray(value)
    ? jiraInputToken(value.child)
    : null
})
function selectionToken(value: unknown) {
  const token = jiraInputToken(value)
  const option = (props.field.allowedValues || []).find((option) =>
    [option.id, option.value].some((value) => value != null && String(value) === String(token))
  )
  return option ? jiraInputToken(option.id ?? option.value) : token
}
const modelValueAsString = computed(() => String(jiraInputToken(props.modelValue) ?? ''))
const modelValueAsNumber = computed(() =>
  typeof props.modelValue == 'number' ? props.modelValue : null
)
const modelValueAsDate = computed(() => normalizeDateValue(props.modelValue))
const modelValueAsArray = computed(() =>
  Array.isArray(props.modelValue)
    ? props.modelValue.map((value) => String(jiraInputToken(value) ?? ''))
    : []
)
const modelValueAsSelect = computed(() =>
  isMultiple.value
    ? Array.isArray(props.modelValue)
      ? props.modelValue
          .map(selectionToken)
          .filter((value): value is string | number => value !== null)
      : []
    : Array.isArray(props.modelValue)
      ? null
      : selectionToken(props.modelValue)
)

function updateBoolean(value: string | null) {
  updateValue(value === null ? null : value === 'true')
}
function updateParent(value: string | number | null) {
  updateValue(value === null ? null : { id: String(value) })
}
function updateChild(value: string | number | null) {
  if (cascadeParent.value === null) return
  updateValue({
    id: String(cascadeParent.value),
    ...(value === null ? {} : { child: { id: String(value) } })
  })
}

function updateValue(value: JiraFieldValue | undefined) {
  emits('update:modelValue', value ?? null)
  emits('change')
}

function updateDateValue(value: string | null) {
  emits('update:modelValue', normalizeDateValue(value))
  emits('change')
}

function updateArrayValue(value: string[]) {
  emits('update:modelValue', value)
  emits('change')
}

function emitChange() {
  emits('change')
}

function normalizeDateValue(value: JiraFieldValue | undefined) {
  if (value == null || value === '') return null

  const dateValue = String(value).slice(0, 10)
  if (!isValidDateValue(dateValue)) return null

  return dateValue
}

function isValidDateValue(value: string) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false

  const date = new Date(`${value}T00:00:00.000Z`)
  return !Number.isNaN(date.getTime()) && date.toISOString().startsWith(value)
}
</script>
