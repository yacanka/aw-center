<script setup lang="ts">
import { ref } from 'vue'
import { usePresentationController } from '@/features/tools/composables/presentationController'
import {
  useMessage,
  NUpload,
  NUploadDragger,
  NIcon,
  NInput,
  UploadCustomRequestOptions
} from 'naive-ui'
import { CloudArrowUp24Regular as UploadIcon } from '@vicons/fluent'
import type { Job } from '@/features/jobs/api/jobs'

const msg = useMessage()
const title = ref('')
const controller = usePresentationController()
let pendingAttempt: { fingerprint: string; key: string } | null = null

async function handleUploadReq({ file, onFinish, onError }: UploadCustomRequestOptions) {
  if (!file.file) return

  const form = new FormData()
  form.append('title', title.value || file.name.replace(/\.pptx?$/i, ''))
  form.append('file', file.file)
  const fingerprint = [
    title.value.trim(),
    file.file.name,
    file.file.size,
    file.file.lastModified
  ].join(':')
  if (pendingAttempt?.fingerprint !== fingerprint) {
    pendingAttempt = { fingerprint, key: crypto.randomUUID() }
  }

  window.$loadingBar.start()
  try {
    const job = await controller.uploadPresentation(form, pendingAttempt.key)
    pendingAttempt = null
    onFinish()
    window.$loadingBar.finish()
    msg.success('Presentation conversion queued.')
    emit('queued', job)
  } catch {
    onError()
    window.$loadingBar.error()
  }
}

const emit = defineEmits<{ queued: [job: Job] }>()
</script>

<template>
  <n-space vertical>
    <n-input v-model:value="title" placeholder="Presentation title (optional)" />
    <n-upload
      directory-dnd
      :custom-request="handleUploadReq"
      :show-file-list="false"
      accept=".pptx"
      :disabled="controller.loading.value"
    >
      <n-upload-dragger>
        <div>
          <n-icon size="48">
            <UploadIcon />
          </n-icon>
          <div v-if="controller.loading.value">
            Please wait while the conversion job is queued...
          </div>
          <div v-else>Click or drag a file to this area to upload</div>
        </div>
      </n-upload-dragger>
    </n-upload>
  </n-space>
</template>
