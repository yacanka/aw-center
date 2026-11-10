<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { NAlert, NButton, NFormItem, NSelect, NSpace, NText } from 'naive-ui'
import { formatApiError } from '@/shared/api/apiError'
import { fetchJiraTrackedIssues } from '../api/jiraRecords'
import {
  fetchWatcherPreferences,
  fetchWatcherStatus,
  updateWatcherPreferences,
  type WatcherDetailField,
  type WatcherPreferences,
  type WatcherStatus
} from '../api/watcher'
import type { IJiraTrackedIssue } from '../models/records'
import { selectWatcherDetailFields, watcherComponentKey } from '../models/watcherDetailFields'

const props = defineProps<{
  onRecordSynced?: (id: string, status: WatcherStatus) => void
  onPreferencesSaved?: (preferences: WatcherPreferences) => void
}>()
const preferences = ref<WatcherPreferences>({
  outstanding_only: false,
  detail_fields: {},
  component_fields: {}
})
const component = ref<string | null>(null)
const sourceRecord = ref<IJiraTrackedIssue | null>(null)
const records = ref<IJiraTrackedIssue[]>([])
const fields = ref<WatcherDetailField[]>([])
const selected = ref<string[]>([])
const loading = ref(false)
const saving = ref(false)
const initialized = ref(false)
const error = ref('')
const success = ref('')
const discoveryNotice = ref('')
const knownStatuses = new Map<string, WatcherStatus>()
let sequence = 0
let disposed = false
onBeforeUnmount(() => {
  disposed = true
  sequence++
})

const componentOptions = computed(() => {
  const names = new Set(records.value.flatMap((record) => record.components ?? []))
  const options = [...names]
    .sort((left, right) => left.localeCompare(right))
    .map((name) => ({ label: name, value: watcherComponentKey(name) }))
  if (records.value.some((record) => record.components?.length === 0))
    options.push({ label: 'None', value: 'none' })
  return options
})
const fieldOptions = computed(() =>
  fields.value.map((field) => ({ label: field.label, value: field.id }))
)
function belongsToComponent(record: IJiraTrackedIssue, key: string) {
  return (
    record.components !== null &&
    record.components !== undefined &&
    (record.components.length ? record.components.map(watcherComponentKey) : ['none']).includes(key)
  )
}

async function readStatus(id: string) {
  const status = await fetchWatcherStatus(id)
  // The server may update the title/version even after selection changes or this modal closes.
  // Refresh the parent record before fencing this component's local UI response.
  props.onRecordSynced?.(id, status)
  return status
}

async function initialize() {
  const request = ++sequence
  loading.value = true
  initialized.value = false
  error.value = ''
  success.value = ''
  discoveryNotice.value = ''
  fields.value = []
  sourceRecord.value = null
  knownStatuses.clear()
  try {
    const settings = await fetchWatcherPreferences()
    if (request !== sequence) return
    preferences.value = settings
    const loaded = new Map<string, IJiraTrackedIssue>()
    let page = 1
    let hasMore = true
    // Read every authorized page so component choices never depend on the current table page.
    while (hasMore) {
      const result = await fetchJiraTrackedIssues({ page, page_size: 100 })
      if (request !== sequence) return
      for (const record of result.results) loaded.set(record.id, record)
      hasMore = Boolean(result.pagination.next)
      page++
    }
    let unresolved = 0
    for (const record of loaded.values()) {
      if (record.components != null) continue
      try {
        const status = await readStatus(record.id)
        if (request !== sequence) return
        record.components = status.components ?? []
        knownStatuses.set(record.id, status)
      } catch {
        if (request !== sequence) return
        unresolved++
      }
    }
    if (unresolved)
      discoveryNotice.value = `${unresolved} tracked issue(s) could not be loaded. Their components remain unknown. Reload components to retry.`
    records.value = [...loaded.values()]
    initialized.value = true
    const next = componentOptions.value.some((option) => option.value === component.value)
      ? component.value
      : componentOptions.value[0]?.value
    if (next) await selectComponent(next)
    else component.value = null
  } catch (reason) {
    if (request === sequence) error.value = formatApiError(reason)
  } finally {
    if (request === sequence) loading.value = false
  }
}

async function selectComponent(key: string) {
  component.value = key
  sourceRecord.value = null
  fields.value = []
  selected.value = []
  const request = ++sequence
  loading.value = true
  error.value = ''
  success.value = ''
  try {
    const candidates = records.value.filter((record) => belongsToComponent(record, key))
    let lastError = ''
    for (const record of candidates) {
      let status: WatcherStatus
      try {
        status = knownStatuses.get(record.id) ?? (await readStatus(record.id))
      } catch (reason) {
        if (request !== sequence) return
        lastError = formatApiError(reason)
        continue
      }
      if (request !== sequence) return
      knownStatuses.delete(record.id)
      record.components = status.components ?? []
      if (!belongsToComponent(record, key)) continue
      sourceRecord.value = record
      fields.value = status.detail_fields
      selected.value =
        preferences.value.component_fields?.[key] ??
        selectWatcherDetailFields(
          status.detail_fields,
          status.project_slugs,
          preferences.value.detail_fields,
          key === 'none' ? [] : [key.slice(10)],
          preferences.value.component_fields
        ).map((field) => field.id)
      return
    }
    error.value =
      lastError ||
      'No tracked issue has this component anymore. Reload components to refresh the list.'
  } catch (reason) {
    if (request === sequence) error.value = formatApiError(reason)
  } finally {
    if (request === sequence) loading.value = false
  }
}

async function save() {
  if (
    !component.value ||
    !sourceRecord.value ||
    !initialized.value ||
    saving.value ||
    loading.value
  )
    return
  const request = sequence
  saving.value = true
  error.value = ''
  success.value = ''
  try {
    const settings = await updateWatcherPreferences({
      record_id: sourceRecord.value.id,
      component_name: component.value === 'none' ? null : component.value.slice(10),
      detail_field_ids: selected.value
    })
    props.onPreferencesSaved?.(settings)
    if (disposed || request !== sequence) return
    preferences.value = settings
    success.value = 'Detail fields saved for this component.'
  } catch (reason) {
    if (!disposed && request === sequence) error.value = formatApiError(reason)
  } finally {
    if (!disposed && request === sequence) saving.value = false
  }
}
onMounted(initialize)
</script>

<template>
  <n-space vertical :size="16">
    <n-text depth="2"
      >Choose the JIRA fields shown in Watcher details for each tracked component. None groups
      issues without components.</n-text
    >
    <n-form-item label="Component">
      <n-select
        :value="component"
        :options="componentOptions"
        :disabled="!initialized || saving"
        :loading="loading"
        filterable
        aria-label="Watcher settings component"
        :input-props="{ 'aria-label': 'Watcher settings component' }"
        @update:value="selectComponent"
      />
    </n-form-item>
    <n-text v-if="initialized && !records.length" depth="2"
      >No tracked issues. Add a JIRA issue to discover its components and available fields.</n-text
    >
    <n-text v-if="sourceRecord" depth="3"
      >Available fields loaded from {{ sourceRecord.issue }}.</n-text
    >
    <n-form-item v-if="fields.length" label="Detail fields">
      <n-select
        :value="selected"
        :options="fieldOptions"
        :disabled="saving || loading"
        multiple
        filterable
        clearable
        :input-props="{ 'aria-label': 'Watcher detail fields' }"
        aria-label="Watcher detail fields"
        @update:value="(value: string[]) => (selected = value)"
      />
    </n-form-item>
    <n-text v-if="fields.length" depth="2"
      >Clear the selection to hide all detail fields. Fields absent from an issue are omitted. For
      issues with multiple components, the selected fields are combined.</n-text
    >
    <n-alert v-if="discoveryNotice" type="warning">{{ discoveryNotice }}</n-alert>
    <n-alert v-if="error" type="error" role="alert">{{ error }}</n-alert>
    <n-alert v-if="success" type="success" role="status">{{ success }}</n-alert>
    <n-space>
      <n-button :disabled="loading || saving" @click="initialize">{{
        initialized ? 'Reload components' : 'Retry loading components'
      }}</n-button>
      <n-button
        v-if="error && initialized && component"
        :loading="loading"
        :disabled="saving"
        @click="selectComponent(component)"
        >Retry loading fields</n-button
      >
      <n-button
        type="primary"
        :loading="saving"
        :disabled="!initialized || !sourceRecord || !fields.length || loading || saving"
        @click="save"
        >Save detail fields</n-button
      >
    </n-space>
  </n-space>
</template>
