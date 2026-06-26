<template>
  <n-search
    v-if="inputType == 'person'"
    :value="modelValueAsString"
    :placeholder="field.name"
    :list="people"
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
import { IPerson } from '@/models/orgs'
import { resolveJiraFieldInputType } from '@/utils/jiraFieldInput'

const props = defineProps<{
  field: IJiraField
  modelValue?: JiraFieldValue
  people: IPerson[]
}>()

const emits = defineEmits<{
  'update:modelValue': [value: JiraFieldValue]
  change: []
}>()

const inputType = computed(() => resolveJiraFieldInputType(props.field))
const modelValueAsString = computed(() =>
  props.modelValue == null ? '' : String(props.modelValue)
)
const modelValueAsNumber = computed(() =>
  typeof props.modelValue == 'number' ? props.modelValue : null
)
const modelValueAsDate = computed(() => normalizeDateValue(props.modelValue))

function updateValue(value: JiraFieldValue | undefined) {
  emits('update:modelValue', value ?? null)
  emits('change')
}

function updateDateValue(value: string | null) {
  emits('update:modelValue', normalizeDateValue(value))
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
