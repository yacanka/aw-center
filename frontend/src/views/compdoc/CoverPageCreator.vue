<template>
  <n-flex justify="center">
    <n-card title="Cover Page Creator from Excel" style="width: 90%">
      <n-space vertical size="large">
        <n-alert type="info" :bordered="false">
          The workbook is checked before queueing. Output is created in private storage and remains
          available from Job Center according to the retention policy.
        </n-alert>
        <n-grid cols="12" x-gap="12" y-gap="12">
          <n-grid-item v-for="column in requiredColumns" :key="column" span="3">
            <n-tag :type="columnStatus(column)">{{ column }}</n-tag>
          </n-grid-item>
        </n-grid>
        <n-upload :max="1" :default-upload="false" accept=".xlsm,.xlsx" @change="handleFileChange">
          <n-upload-dragger>
            <n-text style="font-size: 16px">Click or drag a workbook here</n-text>
            <n-p depth="3">Required columns are inspected without retaining this preview.</n-p>
          </n-upload-dragger>
        </n-upload>
        <n-alert v-if="missingColumns.length" type="error">
          Missing columns: {{ missingColumns.join(', ') }}
        </n-alert>
        <n-button
          type="primary"
          :loading="queueing || inspecting"
          :disabled="!selectedFile || missingColumns.length > 0 || inspecting"
          @click="queueCoverPages"
        >
          Queue cover-page creation
        </n-button>
      </n-space>
    </n-card>
  </n-flex>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import type { UploadFileInfo } from 'naive-ui'
import { inspectExcelColumns } from '@/services/excelTools'
import { createCoverPageJob } from '@/services/jobs'
import { formatApiError } from '@/services/apiError'
import { selectedUploadFile } from '@/utils/uploads'

const requiredColumns = [
  'Cover Page Number',
  'Cover Page Issue',
  'ATA Chapter',
  'Disciplines',
  'Technical Document Name',
  'CAT',
  'Requirements',
  'MoC',
  'Technical Document Number',
  'Technical Document Issue',
  'AS Name',
  'CVE Name'
]
const router = useRouter()
const files = ref<UploadFileInfo[]>([])
const detectedColumns = ref<string[]>([])
const missingColumns = ref<string[]>([])
const inspecting = ref(false)
const queueing = ref(false)
const selectedFile = computed(() => selectedUploadFile(files.value))

async function handleFileChange(value: { fileList: UploadFileInfo[] }): Promise<void> {
  files.value = value.fileList
  detectedColumns.value = []
  missingColumns.value = []
  if (!selectedFile.value) return
  inspecting.value = true
  try {
    detectedColumns.value = await inspectExcelColumns(selectedFile.value)
    const detected = new Set(
      detectedColumns.value.map((column) => column.trim().toLocaleLowerCase())
    )
    missingColumns.value = requiredColumns.filter(
      (column) => !detected.has(column.toLocaleLowerCase())
    )
  } catch (error) {
    missingColumns.value = [...requiredColumns]
    window.$message.error(formatApiError(error))
  } finally {
    inspecting.value = false
  }
}

async function queueCoverPages(): Promise<void> {
  if (!selectedFile.value || missingColumns.value.length) return
  queueing.value = true
  try {
    await createCoverPageJob(selectedFile.value)
    window.$message.success('Cover-page creation queued in Job Center.')
    await router.push('/jobs')
  } catch (error) {
    window.$message.error(formatApiError(error))
  } finally {
    queueing.value = false
  }
}

function columnStatus(column: string): 'default' | 'success' | 'warning' | 'error' {
  if (!selectedFile.value || inspecting.value) return 'warning'
  const detected = detectedColumns.value.some(
    (candidate) => candidate.trim().toLocaleLowerCase() === column.toLocaleLowerCase()
  )
  return detected ? 'success' : 'error'
}
</script>
