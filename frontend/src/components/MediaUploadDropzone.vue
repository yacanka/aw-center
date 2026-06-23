<template>
  <n-upload
    :max="1"
    :default-upload="false"
    accept="image/*,video/*,audio/*"
    class="media-upload"
    @change="emitSelectedFile"
  >
    <n-upload-dragger>
      <div style="font-size: 40px; margin-bottom: 12px">⬆</div>
      <n-text strong>Drop a media file here or click to select</n-text>
      <n-p depth="3">Images, audio, and video files are supported.</n-p>
    </n-upload-dragger>
  </n-upload>
</template>

<script setup lang="ts">
import type { UploadFileInfo } from 'naive-ui'

const emit = defineEmits<{
  selected: [file: File | null]
}>()

function emitSelectedFile(options: { fileList: UploadFileInfo[] }) {
  emit('selected', (options.fileList[0]?.file as File | undefined) ?? null)
}
</script>

<style scoped>
.media-upload :deep(.n-upload-trigger) {
  width: 100%;
}

.media-upload :deep(.n-upload-dragger) {
  align-items: center;
  aspect-ratio: 1 / 1;
  border-radius: 18px;
  display: flex;
  flex-direction: column;
  justify-content: center;
  margin: 0 auto;
  max-width: 360px;
}
</style>
