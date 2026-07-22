<template>
  <n-card title="Compliance Document Analyzer">
    <n-space vertical size="large">
      <n-alert type="info" :bordered="false">
        Analysis uses private local semantic models. Full evidence remains in an owner-authorized
        JSON artifact; Job Center shows a content-free score summary.
      </n-alert>
      <n-upload
        ref="uploadForm"
        :max="1"
        :default-upload="false"
        accept=".docx"
        @change="handleFileChange"
      >
        <n-upload-dragger>
          <n-text style="font-size: 16px">Click or drag a compliance document here</n-text>
          <n-p depth="3">Only modern macro-free Word documents are accepted.</n-p>
        </n-upload-dragger>
      </n-upload>
      <n-form-item label="Analysis checklist">
        <n-select
          v-model:value="selectedChecks"
          multiple
          :options="checkOptions"
          placeholder="Select checks"
        />
      </n-form-item>
      <n-button
        type="primary"
        :loading="queueing"
        :disabled="!selectedFile || selectedChecks.length === 0 || active"
        @click="queueAnalysis"
      >
        Queue private analysis
      </n-button>
      <n-alert v-if="errorMessage" type="error" closable @close="errorMessage = ''">
        {{ errorMessage }}
      </n-alert>
      <PageJobStatus
        :job="job"
        :cancelling="cancelling"
        :retrying="retrying"
        :downloading="downloading"
        @cancel="cancel"
        @retry="retry"
        @download="download"
        @open="openJobCenter"
      />
    </n-space>
  </n-card>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import type { UploadFileInfo, UploadInst } from 'naive-ui'
import PageJobStatus from '@/components/jobs/PageJobStatus.vue'
import { usePageJob } from '@/composables/usePageJob'
import { formatApiError } from '@/services/apiError'
import { createDocumentAnalysisJob } from '@/services/jobs'
import { selectedUploadFile } from '@/utils/uploads'

const checkOptions = [
  { value: 'compliance_documents', label: 'Compliance document list' },
  { value: 'abbreviations', label: 'Abbreviations table' },
  { value: 'attachments', label: 'Attachments section' },
  { value: 'revision_history', label: 'Revision history' },
  { value: 'approvals', label: 'Approval and signature information' }
]
const uploadForm = ref<UploadInst | null>(null)
const files = ref<UploadFileInfo[]>([])
const selectedChecks = ref(checkOptions.map((option) => option.value))
const queueing = ref(false)
const {
  active,
  cancel,
  cancelling,
  download,
  downloading,
  errorMessage,
  job,
  openJobCenter,
  retry,
  retrying,
  setJob
} = usePageJob('analysis_job')
const selectedFile = computed(() => selectedUploadFile(files.value, false))

function handleFileChange(value: { fileList: UploadFileInfo[] }): void {
  files.value = value.fileList
}

async function queueAnalysis(): Promise<void> {
  if (!selectedFile.value || !selectedChecks.value.length) return
  queueing.value = true
  try {
    setJob(await createDocumentAnalysisJob(selectedFile.value, selectedChecks.value))
    uploadForm.value?.clear()
    files.value = []
    window.$message.success('Private analysis queued. Progress is shown below.')
  } catch (error) {
    window.$message.error(formatApiError(error))
  } finally {
    queueing.value = false
  }
}
</script>
