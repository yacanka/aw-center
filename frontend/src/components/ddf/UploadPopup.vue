<template>
  <n-modal v-model:show="showModal" preset="dialog" title="Upload Word" centered width="500px">
    <div class="modal-content">
      <n-upload directory-dnd :show-file-list="false" :max="1" accept=".docm,.docx" :custom-request="handleUploadReq"
        @change="handleChange">
        <n-upload-dragger>
          <n-text style="font-size: 16px">
            Click or drag a file to this area to upload
          </n-text>
          <n-p depth="3" style="margin: 8px 0 0 0">
            Upload DDF Word file
          </n-p>
        </n-upload-dragger>
      </n-upload>
    </div>
  </n-modal>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { NModal, UploadCustomRequestOptions } from 'naive-ui';
import axios from 'axios'
import { useDdfStore } from '@/stores/api'
import { popupStore } from '@/stores/popupStore';

const showModal = ref(false);
const store = useDdfStore()
const uploaderFormRef = ref(null); // UploadForm'a erişim için
const popup = popupStore()

onMounted(() => {

});

function setActive(show: boolean) {
  showModal.value = show
}

function closeModal() {
  showModal.value = false;
}

function handleChange() {
  window.$loadingBar.start()
}

const props = defineProps({
  uploadUrl: String
})


defineExpose({
  setActive
})

function handleUploadReq({ file, onFinish, onError }: UploadCustomRequestOptions) {
  if (!file.file) return
  const formData = new FormData()
  formData.append('file', file.file)

  store.uploadDdf(formData).then((res) => {
    onFinish()
    window.$loadingBar.finish()
  }).catch((err) => {
    console.error(err)
    onError()
    window.$loadingBar.error()
  }).finally(() => {
    setActive(false)
    store.fetchDdf()
  })
}

</script>

<style scoped></style>
