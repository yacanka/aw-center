<template>
  <n-card title="JIRA Subtask Creator" class="app-page-container">
    <n-space vertical size="large">
      <n-alert type="info" :bordered="false">
        JIRA credentials stay in the server-side session. Creation runs as a durable,
        marker-idempotent job.
      </n-alert>

      <n-form-item label="Parent JIRA task URL or issue key">
        <n-input v-model:value="issue" placeholder="CHN-123 or JIRA browse URL" />
      </n-form-item>
      <n-flex justify="end">
        <n-button
          type="primary"
          ghost
          :loading="loadingFields"
          :disabled="!canLoadFields"
          @click="loadFields"
        >
          Load JIRA fields
        </n-button>
      </n-flex>

      <n-tabs v-model:value="mode" type="segment">
        <n-tab-pane name="manual" tab="List">
          <n-space vertical>
            <n-select
              v-model:value="selectedFieldIds"
              multiple
              filterable
              clearable
              :options="fieldOptions"
              placeholder="Optional JIRA fields"
            />
            <n-dynamic-input v-model:value="items" :on-create="newItem" :min="1" :max="100">
              <template #create-button-default>Add subtask</template>
              <template #default="{ value, index }">
                <n-card size="small" :title="`Subtask ${index + 1}`">
                  <n-grid cols="1 700:2" x-gap="12" y-gap="10">
                    <n-form-item-gi label="Summary">
                      <n-input v-model:value="value.summary" maxlength="255" />
                    </n-form-item-gi>
                    <n-form-item-gi label="Assignee">
                      <n-input v-model:value="value.assignee" maxlength="255" />
                    </n-form-item-gi>
                    <n-form-item-gi label="Due date">
                      <n-date-picker
                        v-model:formatted-value="value.due_date"
                        type="date"
                        value-format="yyyy-MM-dd"
                        style="width: 100%"
                      />
                    </n-form-item-gi>
                    <n-form-item-gi label="Description">
                      <n-input
                        v-model:value="value.description"
                        type="textarea"
                        maxlength="30000"
                      />
                    </n-form-item-gi>
                    <n-form-item-gi
                      v-for="field in activeFields"
                      :key="field.id"
                      :label="field.name"
                    >
                      <JiraFieldInput v-model="value.fields[field.id]" :field="field" />
                    </n-form-item-gi>
                  </n-grid>
                </n-card>
              </template>
            </n-dynamic-input>
            <n-flex justify="end">
              <n-button
                type="primary"
                :loading="submitting"
                :disabled="!canCreateManual"
                @click="submitManual"
              >
                Create subtasks
              </n-button>
            </n-flex>
          </n-space>
        </n-tab-pane>

        <n-tab-pane name="excel" tab="Excel">
          <n-space vertical>
            <n-upload
              :max="1"
              accept=".xls,.xlsm,.xlsx"
              :file-list="fileList"
              :custom-request="inspectWorkbook"
              @update:file-list="fileList = $event"
              @remove="clearWorkbook"
            >
              <n-upload-dragger>
                <n-text>Click or drag a workbook here.</n-text>
                <n-p depth="3">The first sheet may contain at most 100 subtask rows.</n-p>
              </n-upload-dragger>
            </n-upload>
            <n-grid v-if="workbookColumns.length" cols="1 700:2" x-gap="12" y-gap="8">
              <n-form-item-gi v-for="column in workbookColumns" :key="column" :label="column">
                <n-select
                  v-model:value="workbookMapping[column]"
                  clearable
                  filterable
                  :options="workbookFieldOptions"
                  placeholder="Ignore or map to JIRA"
                />
              </n-form-item-gi>
            </n-grid>
            <n-flex justify="end">
              <n-button
                type="primary"
                :loading="submitting"
                :disabled="!canCreateWorkbook"
                @click="submitWorkbook"
              >
                Create from workbook
              </n-button>
            </n-flex>
          </n-space>
        </n-tab-pane>
      </n-tabs>

      <n-alert v-if="errorMessage" type="error" closable @close="errorMessage = ''">
        {{ errorMessage }}
      </n-alert>
      <PageJobStatus
        :job="job"
        :cancelling="cancelling"
        :downloading="downloading"
        download-label="Download receipt"
        @cancel="cancel"
        @download="download"
        @open="openJobCenter"
      />
      <n-flex v-if="canResume" justify="end">
        <n-button type="warning" :loading="resuming" @click="resumeJob">
          Reconcile markers and resume
        </n-button>
      </n-flex>
    </n-space>
  </n-card>
</template>

<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import type { UploadCustomRequestOptions, UploadFileInfo } from 'naive-ui'
import JiraFieldInput from '@/features/dcc/components/JiraFieldInput.vue'
import PageJobStatus from '@/features/jobs/components/PageJobStatus.vue'
import { usePageJob } from '@/features/jobs/composables/usePageJob'
import { useDccStore } from '@/features/dcc/stores/dcc'
import type { IJiraField } from '@/features/dcc/models/jira'
import {
  createManualSubtaskJob,
  createWorkbookSubtaskJob,
  fetchSubtaskFields,
  inspectSubtaskWorkbook,
  resumeSubtaskJob,
  type JiraSubtaskItem,
  type WorkbookMapping
} from '@/features/dcc/api/jiraSubtasks'
import { formatApiError } from '@/shared/api/apiError'
import { selectedUploadFile } from '@/shared/utils/uploads'

const dccStore = useDccStore()
const mode = ref<'manual' | 'excel'>('manual')
const issue = ref('')
const fields = ref<IJiraField[]>([])
const selectedFieldIds = ref<string[]>([])
const items = ref<JiraSubtaskItem[]>([newItem()])
const loadingFields = ref(false)
const submitting = ref(false)
const resuming = ref(false)
const fileList = ref<UploadFileInfo[]>([])
const workbookColumns = ref<string[]>([])
const workbookMapping = reactive<Record<string, string | null>>({})
const { job, errorMessage, cancelling, downloading, setJob, cancel, download, openJobCenter } =
  usePageJob('subtask_job')

const fieldOptions = computed(() =>
  fields.value.map((field) => ({ label: field.name, value: field.id }))
)
const activeFields = computed(() =>
  fields.value.filter((field) => selectedFieldIds.value.includes(field.id))
)
const workbookFieldOptions = computed(() => [
  { label: 'Summary', value: 'summary' },
  { label: 'Description', value: 'description' },
  { label: 'Assignee', value: 'assignee' },
  { label: 'Due date', value: 'duedate' },
  ...fieldOptions.value
])
const canLoadFields = computed(() => dccStore.isJiraConnected && Boolean(issue.value.trim()))
const canCreateManual = computed(
  () =>
    canLoadFields.value &&
    !submitting.value &&
    items.value.length > 0 &&
    items.value.every((item) => item.summary.trim())
)
const canCreateWorkbook = computed(
  () =>
    canLoadFields.value &&
    Boolean(selectedUploadFile(fileList.value, false)) &&
    Object.values(workbookMapping).includes('summary')
)
const canResume = computed(
  () => job.value?.status === 'failed' || job.value?.status === 'reconciliation_required'
)

function newItem(): JiraSubtaskItem {
  return { summary: '', description: '', assignee: '', due_date: null, fields: {} }
}

async function loadFields(): Promise<void> {
  if (!canLoadFields.value) return
  loadingFields.value = true
  errorMessage.value = ''
  try {
    const result = await fetchSubtaskFields(issue.value)
    issue.value = result.issue
    fields.value = result.fields
    selectedFieldIds.value = result.fields
      .filter((field) => field.required)
      .map((field) => field.id)
  } catch (error) {
    errorMessage.value = formatApiError(error)
  } finally {
    loadingFields.value = false
  }
}

async function submitManual(): Promise<void> {
  if (!canCreateManual.value) return
  await submit(() => createManualSubtaskJob(issue.value, items.value))
}

async function inspectWorkbook({
  file,
  onFinish,
  onError
}: UploadCustomRequestOptions): Promise<void> {
  if (!(file.file instanceof File)) return onError()
  try {
    workbookColumns.value = await inspectSubtaskWorkbook(file.file)
    workbookColumns.value.forEach((column) => (workbookMapping[column] = null))
    onFinish()
  } catch (error) {
    errorMessage.value = formatApiError(error)
    onError()
  }
}

function clearWorkbook(): void {
  workbookColumns.value = []
  Object.keys(workbookMapping).forEach((key) => delete workbookMapping[key])
}

async function submitWorkbook(): Promise<void> {
  const file = selectedUploadFile(fileList.value)
  if (!file || !canCreateWorkbook.value) return
  const mapping: WorkbookMapping[] = Object.entries(workbookMapping).flatMap(([column, field]) =>
    field ? [{ column, field }] : []
  )
  await submit(() => createWorkbookSubtaskJob(issue.value, file, mapping))
}

async function submit(action: () => Promise<NonNullable<typeof job.value>>): Promise<void> {
  submitting.value = true
  errorMessage.value = ''
  try {
    setJob(await action())
    window.$message.success('JIRA subtask job queued.')
  } catch (error) {
    errorMessage.value = formatApiError(error)
  } finally {
    submitting.value = false
  }
}

async function resumeJob(): Promise<void> {
  if (!job.value || !canResume.value) return
  resuming.value = true
  errorMessage.value = ''
  try {
    setJob(await resumeSubtaskJob(job.value.id))
    window.$message.success('Marker reconciliation queued.')
  } catch (error) {
    errorMessage.value = formatApiError(error)
  } finally {
    resuming.value = false
  }
}
</script>
