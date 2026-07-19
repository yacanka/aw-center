<template>
  <n-card title="Word Translator">
    <n-space vertical size="large">
      <n-alert type="info" :bordered="false">
        Translation runs as a durable background job. You can leave this page, monitor progress,
        cancel the operation, and download the result from Job Center.
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
          :disabled="!selectedFile || !translationType"
          @click="queueTranslation"
        >
          Queue translation
        </n-button>
      </n-form>
    </n-space>
  </n-card>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import type { UploadFileInfo, UploadInst } from 'naive-ui'
import { createWordTranslationJob } from '@/services/jobs'
import { formatApiError } from '@/services/apiError'
import { selectedUploadFile } from '@/utils/uploads'

const router = useRouter()
const uploadForm = ref<UploadInst | null>(null)
const files = ref<UploadFileInfo[]>([])
const translationType = ref<string | null>(null)
const queueing = ref(false)
const selectedFile = computed(() => selectedUploadFile(files.value))
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
    await createWordTranslationJob(selectedFile.value, translationType.value)
    uploadForm.value?.clear()
    files.value = []
    window.$message.success('Word translation queued in Job Center.')
    await router.push('/jobs')
  } catch (error) {
    window.$message.error(formatApiError(error))
  } finally {
    queueing.value = false
  }
}
</script>
