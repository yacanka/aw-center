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
          :loading="loadingChecks"
          placeholder="Select checks"
        />
      </n-form-item>
      <n-form-item label="My saved questions">
        <n-space vertical style="width: 100%">
          <n-space align="center">
            <n-input
              v-model:value="newQuestion"
              maxlength="500"
              show-count
              placeholder="Ask a question to search in the document"
              style="min-width: min(520px, 70vw)"
              @keyup.enter="saveQuestion"
            />
            <n-button
              secondary
              type="primary"
              :loading="savingQuestion"
              :disabled="!newQuestion.trim()"
              @click="saveQuestion"
            >
              Save and select
            </n-button>
          </n-space>
          <n-list v-if="customChecks.length" bordered>
            <n-list-item v-for="check in customChecks" :key="check.id">
              {{ check.question }}
              <template #suffix>
                <n-popconfirm @positive-click="removeQuestion(check)">
                  <template #trigger>
                    <n-button text type="error">Delete</n-button>
                  </template>
                  Delete this saved question from your profile?
                </n-popconfirm>
              </template>
            </n-list-item>
          </n-list>
          <n-text v-else-if="!loadingChecks" depth="3">
            Add reusable questions here. They are private to your user profile.
          </n-text>
        </n-space>
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
import { useDocumentAnalysisChecks } from '@/composables/useDocumentAnalysisChecks'
import { usePageJob } from '@/composables/usePageJob'
import { formatApiError } from '@/services/apiError'
import { customAnalysisCheckValue } from '@/services/documentAnalysis'
import { createDocumentAnalysisJob } from '@/services/jobs'
import { selectedUploadFile } from '@/utils/uploads'

const defaultCheckOptions = [
  { value: 'compliance_documents', label: 'Compliance document list' },
  { value: 'abbreviations', label: 'Abbreviations table' },
  { value: 'attachments', label: 'Attachments section' },
  { value: 'revision_history', label: 'Revision history' },
  { value: 'approvals', label: 'Approval and signature information' }
]
const uploadForm = ref<UploadInst | null>(null)
const files = ref<UploadFileInfo[]>([])
const selectedChecks = ref(defaultCheckOptions.map((option) => option.value))
const queueing = ref(false)
const { customChecks, loadingChecks, newQuestion, removeQuestion, saveQuestion, savingQuestion } =
  useDocumentAnalysisChecks(selectedChecks)
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
const checkOptions = computed(() => [
  ...defaultCheckOptions,
  ...customChecks.value.map((check) => ({
    value: customAnalysisCheckValue(check.id),
    label: check.question
  }))
])
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
