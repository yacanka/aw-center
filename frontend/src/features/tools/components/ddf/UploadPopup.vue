<template>
  <n-modal
    v-model:show="showModal"
    preset="dialog"
    title="Upload Word"
    centered
    class="app-modal app-modal--small"
  >
    <div class="modal-content">
      <n-upload
        directory-dnd
        :show-file-list="false"
        :max="1"
        accept=".docm,.docx"
        :custom-request="handleUploadReq"
        @change="handleChange"
      >
        <n-upload-dragger>
          <n-text style="font-size: 16px"> Click or drag a file to this area to upload </n-text>
          <n-p depth="3" style="margin: 8px 0 0 0"> Upload DDF Word file </n-p>
        </n-upload-dragger>
      </n-upload>
    </div>
  </n-modal>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { NModal, UploadCustomRequestOptions } from 'naive-ui'
import { useDdfController } from '@/features/tools/composables/ddfController'

const showModal = ref(false)
const store = useDdfController()

function setActive(show: boolean) {
  showModal.value = show
}

function handleChange() {
  window.$loadingBar.start()
}

defineExpose({
  setActive
})

function handleUploadReq({ file, onFinish, onError }: UploadCustomRequestOptions) {
  if (!file.file) return
  const formData = new FormData()
  formData.append('file', file.file)

  store
    .uploadDdf(formData)
    .then(() => {
      onFinish()
      window.$loadingBar.finish()
    })
    .catch((err) => {
      console.error(err)
      onError()
      window.$loadingBar.error()
    })
    .finally(() => {
      setActive(false)
      store.fetchDdf()
    })
}
</script>

<style scoped></style>
