<template>
  <n-flex justify="center">
    <n-card title="JIRA Subtask Generator from Excel" style="width: 90%">
      <n-grid cols="6" x-gap="12" y-gap="18">
        <n-grid-item span="4">
          <n-input
            v-model:value="generator.url"
            placeholder="Enter Jira task URL or key"
            :disabled="busy"
            @blur="ensureFieldsLoaded"
            @keydown.enter.prevent="loadSubtaskFields"
          />
        </n-grid-item>
        <n-grid-item span="2">
          <n-flex>
            <n-button
              :loading="fieldLoading"
              :disabled="fieldLoadDisabled"
              @click="loadSubtaskFields"
            >
              Load Fields
            </n-button>
            <n-button type="info" ghost :disabled="generateDisabled" @click="createSubtasks">
              Generate
            </n-button>
          </n-flex>
        </n-grid-item>
        <n-grid-item span="6">
          <n-text v-if="fieldLoading">Loading fields for this task…</n-text>
          <n-text v-else-if="fieldError" type="error">{{ fieldError }}</n-text>
          <n-text v-else-if="fieldsReady">
            {{ loadedIssue }}: {{ jiraFields.length }} subtask fields loaded. Required fields are
            marked *.
          </n-text>
          <n-text v-else depth="3"
            >Enter a parent task and load its JIRA fields before mapping columns.</n-text
          >
          <n-p v-if="unsupportedRequired.length" style="margin-bottom: 0">
            <n-text type="error"
              >Unsupported required fields:
              {{ unsupportedRequired.map((field) => field.name).join(', ') }}.</n-text
            >
          </n-p>
          <n-p v-else-if="missingRequired.length && generator.list.length" style="margin-bottom: 0">
            <n-text type="warning"
              >Map required fields:
              {{ missingRequired.map((field) => field.name).join(', ') }}.</n-text
            >
          </n-p>
        </n-grid-item>
        <n-grid-item v-if="loadingBar.show" span="6">
          <n-ellipsis v-if="loadingBar.content">{{ loadingBar.content }}</n-ellipsis>
          <n-progress
            type="line"
            :status="loadingBar.status"
            :percentage="loadingBar.percentage"
            indicator-placement="outside"
            :height="30"
            :processing="loadingBar.status === 'default'"
          />
        </n-grid-item>
        <n-grid-item span="6">
          <n-upload
            :max="1"
            accept=".xlsm,.xlsx"
            :disabled="busy"
            :custom-request="handleUploadReq"
            @change="handleFileChange"
            @remove="handleFileRemove"
          >
            <n-upload-dragger>
              <n-text style="font-size: 16px">Click or drag a file to this area to upload</n-text>
              <n-p depth="3" style="margin: 8px 0 0 0"
                >Upload the Excel file containing the data to generate subtasks from.</n-p
              >
            </n-upload-dragger>
          </n-upload>
        </n-grid-item>
        <n-grid-item v-if="generator.list.length" span="3">
          <n-h4 style="margin-bottom: -10px">Excel Column Names</n-h4>
        </n-grid-item>
        <n-grid-item v-if="generator.list.length" span="3">
          <n-h4 style="margin-bottom: -10px">JIRA Field Names</n-h4>
        </n-grid-item>
        <n-grid-item v-for="mapping in generator.list" :key="mapping.excel" span="6">
          <n-grid cols="6" x-gap="12" y-gap="18">
            <n-grid-item span="3"><n-input :value="mapping.excel" readonly /></n-grid-item>
            <n-grid-item span="3">
              <n-select
                v-model:value="mapping.jira"
                :options="optionsFor(mapping.jira)"
                :disabled="!fieldsReady || busy"
                :loading="fieldLoading"
                placeholder="Select Field"
                filterable
                clearable
              />
              <n-text v-if="mapping.jira" depth="3">{{ fieldHint(mapping.jira) }}</n-text>
            </n-grid-item>
          </n-grid>
        </n-grid-item>
      </n-grid>
    </n-card>
  </n-flex>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import type { UploadCustomRequestOptions, UploadFileInfo } from 'naive-ui'
import { useDccStore } from '@/features/dcc/stores/dcc'
import { useSubtaskProgress } from '@/features/dcc/composables/useSubtaskProgress'
import {
  createWorkbookSubtaskJob,
  fetchSubtaskFields,
  inspectSubtaskWorkbook
} from '@/features/dcc/api/jiraSubtasks'
import type { IJiraField } from '@/features/dcc/models/jira'
import { formatApiError } from '@/shared/api/apiError'
import { selectedUploadFile } from '@/shared/utils/uploads'

type ListItem = { excel: string; jira: string | null }
const generator = ref({ url: '', list: [] as ListItem[] })
const fileList = ref<UploadFileInfo[]>([])
const inspecting = ref(false)
const jiraFields = ref<IJiraField[]>([])
const fieldLoading = ref(false)
const fieldError = ref('')
const loadedReference = ref('')
const loadedIssue = ref('')
const dccStore = useDccStore()
const { loadingBar, busy, submit } = useSubtaskProgress('excel_subtask_job')
let inspectionVersion = 0
let fieldVersion = 0
const fieldsReady = computed(
  () =>
    Boolean(loadedIssue.value) &&
    loadedReference.value === generator.value.url.trim() &&
    !fieldLoading.value &&
    dccStore.isJiraConnected
)
const fieldLoadDisabled = computed(
  () => busy.value || fieldLoading.value || !generator.value.url.trim() || !dccStore.isJiraConnected
)
const selectedFields = computed(() => new Set(generator.value.list.map((item) => item.jira)))
const requiredFields = computed(() =>
  jiraFields.value.filter(
    (field) =>
      field.id === 'summary' || (field.required && !field.hasDefaultValue && field.id !== 'labels')
  )
)
const missingRequired = computed(() =>
  requiredFields.value.filter((field) => !selectedFields.value.has(field.id))
)
const unsupportedRequired = computed(() =>
  requiredFields.value.filter((field) => field.supported === false)
)
const generateDisabled = computed(
  () =>
    busy.value ||
    inspecting.value ||
    !fieldsReady.value ||
    !generator.value.list.length ||
    !selectedFields.value.has('summary') ||
    Boolean(missingRequired.value.length) ||
    Boolean(unsupportedRequired.value.length)
)

watch(
  [() => generator.value.url.trim(), () => dccStore.isJiraConnected],
  () => {
    fieldVersion += 1
    fieldLoading.value = false
    fieldError.value = ''
    jiraFields.value = []
    loadedReference.value = ''
    loadedIssue.value = ''
    generator.value.list.forEach((item) => {
      item.jira = null
    })
  },
  { flush: 'sync' }
)
onBeforeUnmount(() => {
  fieldVersion += 1
  inspectionVersion += 1
})

function optionsFor(current: string | null) {
  return jiraFields.value.map((field) => ({
    value: field.id,
    label: `${field.name}${requiredFields.value.some((required) => required.id === field.id) ? ' *' : ''}`,
    disabled:
      field.supported === false || (selectedFields.value.has(field.id) && field.id !== current)
  }))
}

function fieldHint(identifier: string) {
  const field = jiraFields.value.find((field) => field.id === identifier)
  const schema = field?.schema
  if (schema?.type === 'array')
    return `${schema.items} list: separate values with semicolons, or use a JSON array.`
  if (schema?.type === 'date')
    return 'Date: YYYY-MM-DD or DD.MM.YYYY; Excel date cells are supported.'
  if (schema?.type === 'datetime')
    return 'Date and time: use text with a timezone, e.g. 2026-09-22T10:00:00+03:00.'
  if (
    schema?.type === 'option-with-child' ||
    String(schema?.custom || '').endsWith(':cascadingselect')
  )
    return 'Parent/child selection: {"id":"parent-id","child":{"id":"child-id"}}.'
  if (schema?.type === 'boolean') return 'Boolean: true or false.'
  if (field?.allowedValues?.length) return 'Use an available option ID or a unique option name.'
  if (schema?.type === 'user') return 'Use the JIRA username or an available user identifier.'
  return String(schema?.type || '')
}

async function ensureFieldsLoaded() {
  if (!fieldsReady.value) await loadSubtaskFields()
}

async function loadSubtaskFields(): Promise<void> {
  if (fieldLoadDisabled.value) return
  const version = ++fieldVersion
  const reference = generator.value.url.trim()
  fieldLoading.value = true
  fieldError.value = ''
  loadedReference.value = ''
  try {
    const result = await fetchSubtaskFields(reference, true)
    if (version !== fieldVersion) return
    jiraFields.value = result.fields
    loadedReference.value = reference
    loadedIssue.value = result.issue
    const available = new Set(
      result.fields.filter((field) => field.supported !== false).map((field) => field.id)
    )
    generator.value.list.forEach((item) => {
      if (!available.has(item.jira || '')) item.jira = null
    })
    if (!available.has('summary'))
      fieldError.value = 'Summary is unavailable on the JIRA subtask create screen.'
  } catch (error) {
    if (version !== fieldVersion) return
    jiraFields.value = []
    loadedIssue.value = ''
    generator.value.list.forEach((item) => {
      item.jira = null
    })
    fieldError.value = formatApiError(error)
  } finally {
    if (version === fieldVersion) fieldLoading.value = false
  }
}

function handleFileChange(options: { fileList: UploadFileInfo[] }): void {
  fileList.value = options.fileList
}

function handleFileRemove(): void {
  inspectionVersion += 1
  inspecting.value = false
  fileList.value = []
  generator.value.list = []
}

async function handleUploadReq({
  file,
  onError,
  onFinish
}: UploadCustomRequestOptions): Promise<void> {
  const selectedFile = selectedUploadFile([file])
  if (!selectedFile) return onError()
  const version = ++inspectionVersion
  inspecting.value = true
  generator.value.list = []
  window.$loadingBar.start()
  try {
    const columns = await inspectSubtaskWorkbook(selectedFile)
    if (version !== inspectionVersion) return
    generator.value.list = columns.map((excel) => ({ excel, jira: null }))
    onFinish()
    await ensureFieldsLoaded()
  } catch (error) {
    if (version !== inspectionVersion) return
    onError()
    window.$notification.error({
      title: 'Error',
      description: formatApiError(error),
      duration: 5000
    })
  } finally {
    if (version === inspectionVersion) inspecting.value = false
    window.$loadingBar.finish()
  }
}

async function createSubtasks(): Promise<void> {
  if (generateDisabled.value) return
  const file = selectedUploadFile(fileList.value)
  if (!file) return
  const mapping = generator.value.list
    .filter((item): item is ListItem & { jira: string } => item.jira !== null)
    .map((item) => ({ column: item.excel, field: item.jira }))
  const issue = loadedIssue.value
  await submit(() => createWorkbookSubtaskJob(issue, file, mapping))
}
</script>
