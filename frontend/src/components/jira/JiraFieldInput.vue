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
    :formatted-value="modelValueAsString"
    value-format="yyyy-MM-dd"
    type="date"
    clearable
    style="width: 100%"
    :placeholder="field.name"
    @update:formatted-value="updateValue"
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
const modelValueAsString = computed(() => (props.modelValue == null ? '' : String(props.modelValue)))
const modelValueAsNumber = computed(() => (typeof props.modelValue == 'number' ? props.modelValue : null))

function updateValue(value: JiraFieldValue | undefined) {
  emits('update:modelValue', value ?? null)
  emits('change')
}

function emitChange() {
  emits('change')
}

</script>
