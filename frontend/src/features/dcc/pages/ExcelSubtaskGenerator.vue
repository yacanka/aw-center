<template>
  <n-flex justify="center">
    <n-card title="JIRA Subtask Generator from Excel" style="width: 90%">
      <n-grid cols="6" x-gap="12" y-gap="18">
        <n-grid-item span="5">
          <n-input
            v-model:value="generator.url"
            type="url"
            placeholder="Enter Url"
            @keydown.enter.prevent
          />
        </n-grid-item>
        <n-grid-item span="1">
          <n-button type="info" ghost :disabled="checkGenerateStatus()" @click="createSubtasks"
            >Generate</n-button
          >
        </n-grid-item>
        <n-grid-item span="5">
          <n-progress
            v-if="loadingBar.show"
            type="line"
            :status="loadingBar.status"
            :percentage="loadingBar.percentage"
            indicator-placement="outside"
            :height="30"
            :processing="loadingBar.status == 'default' ? true : false"
          >
          </n-progress>
        </n-grid-item>
        <n-grid-item span="1">
          <n-ellipsis v-if="loadingBar.status == 'default' ? true : false" style="margin-top: 4px">
            {{ loadingBar.content }}</n-ellipsis
          >
        </n-grid-item>
        <n-grid-item span="6">
          <n-upload
            :max="1"
            accept=".xlsm,.xlsx"
            :custom-request="handleUploadReq"
            @change="handleFileChange"
            @remove="handleFileRemove"
          >
            <n-upload-dragger>
              <n-text style="font-size: 16px"> Click or drag a file to this area to upload </n-text>
              <n-p depth="3" style="margin: 8px 0 0 0">
                Upload the Excel file containing the data to generate subtasks from.
              </n-p>
            </n-upload-dragger>
          </n-upload>
        </n-grid-item>

        <n-grid-item span="3" v-if="fileList.length != 0">
          <n-h4 style="margin-bottom: -10px"> Excel Column Names </n-h4>
        </n-grid-item>
        <n-grid-item span="3" v-if="fileList.length != 0">
          <n-h4 style="margin-bottom: -10px"> JIRA Field Names </n-h4>
        </n-grid-item>

        <n-grid-item span="6" v-for="(field, index) in generator.list" :key="index">
          <n-grid cols="6" x-gap="12" y-gap="18">
            <n-grid-item span="3">
              <n-input v-model:value="field.excel" readonly />
            </n-grid-item>
            <n-grid-item span="3">
              <n-select
                v-model:value="field.jira"
                :options="jiraOptions"
                placeholder="Select Field"
                clearable
                @update:value="handleFieldChange"
              />
            </n-grid-item>
          </n-grid>
        </n-grid-item>
      </n-grid>
    </n-card>
  </n-flex>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import type { UploadCustomRequestOptions, UploadFileInfo } from 'naive-ui'
import { useDccStore } from '@/features/dcc/stores/dcc'
import { useSubtaskProgress } from '@/features/dcc/composables/useSubtaskProgress'
import { createWorkbookSubtaskJob, inspectSubtaskWorkbook } from '@/features/dcc/api/jiraSubtasks'
import { formatApiError } from '@/shared/api/apiError'
import { selectedUploadFile } from '@/shared/utils/uploads'

type ListItem = { excel: string; jira: string | null }
type JiraOption = { value: string; label: string; disabled?: boolean }

const generator = ref({ url: '', list: [] as ListItem[] })
const fileList = ref<UploadFileInfo[]>([])
const inspecting = ref(false)
const dccStore = useDccStore()
const { loadingBar, busy, submit } = useSubtaskProgress('excel_subtask_job')
let inspectionVersion = 0

const jiraOptions = ref<JiraOption[]>([
  { value: 'summary', label: 'Summary' },
  { value: 'description', label: 'Description' },
  { value: 'assignee', label: 'Assignee' },
  { value: 'duedate', label: 'Due Date' }
])

function checkGenerateStatus(): boolean {
  return (
    busy.value ||
    inspecting.value ||
    !dccStore.isJiraConnected ||
    !generator.value.url.trim() ||
    fileList.value.length === 0
  )
}

function handleFileChange(options: { fileList: UploadFileInfo[] }): void {
  fileList.value = options.fileList
}

function handleFileRemove(): void {
  inspectionVersion += 1
  inspecting.value = false
  generator.value.list = []
  handleFieldChange()
}

function handleFieldChange(): void {
  const selected = new Set(generator.value.list.map((item) => item.jira))
  jiraOptions.value.forEach((option) => {
    option.disabled = selected.has(option.value)
  })
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
  handleFieldChange()
  window.$loadingBar.start()
  try {
    const columns = await inspectSubtaskWorkbook(selectedFile)
    if (version !== inspectionVersion) return
    generator.value.list = columns.map((excel) => ({ excel, jira: null }))
    onFinish()
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
  if (checkGenerateStatus()) return
  const file = selectedUploadFile(fileList.value)
  if (!file) return
  const mapping = generator.value.list
    .filter((item): item is ListItem & { jira: string } => item.jira !== null)
    .map((item) => ({ column: item.excel, field: item.jira }))
  if (
    !mapping.some((item) => item.field === 'summary') ||
    !mapping.some((item) => item.field === 'description')
  ) {
    window.$notification.warning({
      title: 'Warning',
      description: 'Summary and Description fields must be selected.',
      duration: 3000
    })
    return
  }
  const issue = generator.value.url
  await submit(() => createWorkbookSubtaskJob(issue, file, mapping))
}
</script>
