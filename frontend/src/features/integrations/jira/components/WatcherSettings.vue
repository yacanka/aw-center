<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { NAlert, NButton, NFormItem, NSelect, NSpace, NText } from 'naive-ui'
import { useProjectCatalogStore } from '@/features/projects/stores/projectCatalog'
import { formatApiError } from '@/shared/api/apiError'
import { fetchJiraTrackedIssues } from '../api/jiraRecords'
import {
  fetchWatcherPreferences,
  fetchWatcherStatus,
  updateWatcherPreferences,
  type WatcherDetailField,
  type WatcherPreferences
} from '../api/watcher'
import type { IJiraTrackedIssue } from '../models/records'

const catalog = useProjectCatalogStore()
const preferences = ref<WatcherPreferences>({ outstanding_only: false, detail_fields: {} })
const project = ref<string | null>(null)
const recordId = ref<string | null>(null)
const records = ref<IJiraTrackedIssue[]>([])
const fields = ref<WatcherDetailField[]>([])
const selected = ref<string[]>([])
const loading = ref(false)
const saving = ref(false)
const initialized = ref(false)
const error = ref('')
const success = ref('')
const hasMore = ref(false)
const currentPage = ref(1)
const failedPage = ref<number | null>(null)
let sequence = 0
onBeforeUnmount(() => sequence++)
const projectOptions = computed(() =>
  catalog.jiraProjects.map((item) => ({ label: item.name, value: item.slug }))
)
const recordOptions = computed(() =>
  records.value.map((item) => ({ label: `${item.issue} — ${item.title}`, value: item.id }))
)
const fieldOptions = computed(() =>
  fields.value.map((item) => ({ label: item.label, value: item.id }))
)

async function selectProject(slug: string) {
  project.value = slug
  hasMore.value = false
  recordId.value = null
  records.value = []
  fields.value = []
  selected.value = [
    ...(preferences.value.detail_fields[slug] ?? [
      'customfield_45000',
      'customfield_45001',
      'customfield_45002'
    ])
  ]
  currentPage.value = 1
  failedPage.value = null
  await loadRecords()
}
async function loadRecords(targetPage = failedPage.value ?? currentPage.value) {
  if (!project.value) return
  const request = ++sequence
  loading.value = true
  error.value = ''
  success.value = ''
  try {
    const result = await fetchJiraTrackedIssues({
      project_slug: project.value,
      page: targetPage,
      page_size: 100
    })
    if (request !== sequence) return
    records.value = targetPage === 1 ? result.results : [...records.value, ...result.results]
    currentPage.value = targetPage
    failedPage.value = null
    hasMore.value = Boolean(result.pagination.next)
  } catch (reason) {
    if (request === sequence) {
      failedPage.value = targetPage
      error.value = formatApiError(reason)
    }
  } finally {
    if (request === sequence) loading.value = false
  }
}
async function loadMore() {
  await loadRecords(currentPage.value + 1)
}
async function selectRecord(id: string) {
  recordId.value = id
  failedPage.value = null
  fields.value = []
  const request = ++sequence
  loading.value = true
  error.value = ''
  success.value = ''
  try {
    const status = await fetchWatcherStatus(id)
    if (request !== sequence) return
    fields.value = status.detail_fields
  } catch (reason) {
    if (request === sequence) error.value = formatApiError(reason)
  } finally {
    if (request === sequence) loading.value = false
  }
}
async function save() {
  if (!project.value || !fields.value.length || !initialized.value || saving.value || loading.value)
    return
  saving.value = true
  error.value = ''
  success.value = ''
  try {
    preferences.value = await updateWatcherPreferences({
      project_slug: project.value,
      detail_field_ids: selected.value
    })
    success.value = 'Detail fields saved. They will be used when you open Watcher.'
  } catch (reason) {
    error.value = formatApiError(reason)
  } finally {
    saving.value = false
  }
}
async function initialize() {
  loading.value = true
  error.value = ''
  const request = ++sequence
  try {
    const result = await fetchWatcherPreferences()
    if (request !== sequence) return
    preferences.value = result
    initialized.value = true
    if (projectOptions.value[0]) await selectProject(projectOptions.value[0].value)
  } catch (reason) {
    if (request === sequence) error.value = formatApiError(reason)
  } finally {
    if (request === sequence) loading.value = false
  }
}
onMounted(initialize)
</script>

<template>
  <n-space vertical :size="16">
    <n-text depth="2"
      >Choose the JIRA fields shown above the subtasks in Watcher details. Selections are saved for
      your account and each project.</n-text
    >
    <n-form-item label="Project">
      <n-select
        :value="project"
        :options="projectOptions"
        :disabled="!initialized || saving"
        aria-label="Watcher settings project"
        @update:value="selectProject"
      />
    </n-form-item>
    <n-form-item label="Load available fields from a tracked issue">
      <n-select
        :value="recordId"
        :options="recordOptions"
        :loading="loading"
        :disabled="!initialized || loading || saving || !records.length"
        filterable
        :input-props="{ 'aria-label': 'Tracked issue for detail fields' }"
        aria-label="Tracked issue for detail fields"
        @update:value="selectRecord"
      />
    </n-form-item>
    <n-button v-if="hasMore" :disabled="loading || saving" @click="loadMore"
      >Load more tracked issues</n-button
    >
    <n-text v-if="initialized && !loading && !records.length && !error" depth="2"
      >Add a JIRA issue to Watcher for this project to discover its available fields.</n-text
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
      issues spanning projects, the selected fields are combined.</n-text
    >
    <n-alert v-if="error" type="error" role="alert">{{ error }}</n-alert>
    <n-alert v-if="success" type="success" role="status">{{ success }}</n-alert>
    <n-button v-if="error && !initialized" :loading="loading" @click="initialize"
      >Retry settings</n-button
    >
    <n-button
      v-if="error && initialized && (failedPage !== null || !fields.length)"
      :loading="loading"
      @click="
        failedPage !== null ? loadRecords() : recordId ? selectRecord(recordId) : loadRecords()
      "
      >Retry loading fields</n-button
    >
    <n-button
      type="primary"
      :loading="saving"
      :disabled="!initialized || !fields.length || loading || saving"
      @click="save"
      >Save detail fields</n-button
    >
  </n-space>
</template>
