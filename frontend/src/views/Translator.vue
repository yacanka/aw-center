<template>
  <n-card title="Word Translator">
    <n-space vertical size="large">
      <n-alert type="info" :bordered="false">
        Translation runs as a durable background job. Progress and controls remain on this page; you
        can still leave and find its history in Job Center.
      </n-alert>
      <n-upload
        ref="uploadForm"
        :show-file-list="true"
        :max="1"
        :default-upload="false"
        accept=".docx"
        @change="handleFileChange"
      >
        <n-upload-dragger>
          <n-text style="font-size: 16px">Click or drag a Word file here</n-text>
          <n-p depth="3">The original document is stored in private job storage.</n-p>
        </n-upload-dragger>
      </n-upload>
      <n-form label-placement="top">
        <n-form-item label="Translation direction">
          <n-select
            v-model:value="translationType"
            :options="translationOptions"
            placeholder="Select direction"
          />
        </n-form-item>
        <n-button
          type="primary"
          :loading="queueing"
          :disabled="!selectedFile || !translationType || active"
          @click="queueTranslation"
        >
          Queue translation
        </n-button>
      </n-form>
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
import { createWordTranslationJob } from '@/services/jobs'
import { formatApiError } from '@/services/apiError'
import { selectedUploadFile } from '@/utils/uploads'

const uploadForm = ref<UploadInst | null>(null)
const files = ref<UploadFileInfo[]>([])
const translationType = ref<string | null>(null)
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
} = usePageJob('translation_job')
const selectedFile = computed(() => selectedUploadFile(files.value, false))
const translationOptions = [
  { value: 'tr2en', label: 'Turkish → English' },
  { value: 'en2tr', label: 'English → Turkish' }
]

function handleFileChange(value: { fileList: UploadFileInfo[] }): void {
  files.value = value.fileList
}

async function queueTranslation(): Promise<void> {
  if (!selectedFile.value || !translationType.value) return
  queueing.value = true
  try {
    setJob(await createWordTranslationJob(selectedFile.value, translationType.value))
    uploadForm.value?.clear()
    files.value = []
    window.$message.success('Word translation queued. Progress is shown below.')
  } catch (error) {
    window.$message.error(formatApiError(error))
  } finally {
    queueing.value = false
  }
}
</script>
