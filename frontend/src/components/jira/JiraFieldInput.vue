<template>
  <n-select
    v-if="allowedOptions.length"
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
import NSearch from '@/components/NSearch.vue'
import { IJiraField, JiraFieldValue } from '@/models/jira'
import { resolveJiraFieldInputType } from '@/utils/jiraFieldInput'

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
const allowedOptions = computed(() =>
  (props.field.allowedValues || []).flatMap((option) => {
    const value = option.value
    const label = option.label
    return typeof value == 'string' || typeof value == 'number'
      ? [{ value, label: String(label ?? value) }]
      : []
  })
)
const modelValueAsString = computed(() =>
  props.modelValue == null || Array.isArray(props.modelValue) ? '' : String(props.modelValue)
)
const modelValueAsNumber = computed(() =>
  typeof props.modelValue == 'number' ? props.modelValue : null
)
const modelValueAsDate = computed(() => normalizeDateValue(props.modelValue))
const modelValueAsArray = computed(() =>
  Array.isArray(props.modelValue) ? props.modelValue.map(String) : []
)
const modelValueAsSelect = computed(() =>
  isMultiple.value
    ? Array.isArray(props.modelValue)
      ? props.modelValue
      : []
    : Array.isArray(props.modelValue)
      ? null
      : props.modelValue
)

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
