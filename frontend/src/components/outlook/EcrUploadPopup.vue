<template>
  <n-modal v-model:show="showUploadModal" preset="dialog" title="Upload ECR Manually" centered width="500px">
    <div class="modal-content">
      <n-upload directory-dnd :show-file-list="false" :max="1" accept=".pdf" :custom-request="handleUploadReq">
        <n-upload-dragger>
          <n-text style="font-size: 16px">
            Click or drag a ECR to this area to upload
          </n-text>
          <n-p depth="3" style="margin: 8px 0 0 0">
            ECR file will be read and parsed
          </n-p>
        </n-upload-dragger>
      </n-upload>
      <n-flex justify="center" style="margin: 12px 0 0 0">
        After that, you can check ECR information and approve.
      </n-flex>
    </div>
  </n-modal>
</template>

<script setup lang="ts">
import { ref, onMounted, PropType } from 'vue';
import { UploadCustomRequestOptions } from 'naive-ui';
import axios from 'axios';
import { IEcd } from '@/models/ecd';
import { binaryToBase64 } from '@/utils/general';

const showUploadModal = ref(false)

const props = defineProps<{
  autoParse?: boolean
}>()

const emit = defineEmits<{
  (event: 'onSuccess', file: File, parsed: string | null): void
}>()

defineExpose({
  openModal
})

function openModal() {
  showUploadModal.value = true
}

function closeModal() {
  showUploadModal.value = false
}

function handleUploadReq({ file, onFinish, onError }: UploadCustomRequestOptions) {
  const uploadfile = file.file
  if (!uploadfile) return
  if (props.autoParse == true) {
    const formData = new FormData()
    formData.append('file', uploadfile)
    axios.post(axios.defaults.baseURL + '/dcc/upload/', formData).then((res) => {
      onFinish()
      window.$notification.success({
        title: 'Success',
        description: 'ECR read successfully.',
        duration: 3000
      })
      window.$loadingBar.finish()
      emit("onSuccess", uploadfile, res.data)
    }).catch(() => {
      onError()
      window.$notification.error({
        title: 'Error',
        description: 'Error while reading ECR.',
        duration: 3000
      })
      window.$loadingBar.error()
    }).finally(() => {

    })
  } else {
    emit("onSuccess", uploadfile, null)
  }
  closeModal()
}

onMounted(() => {

});
</script>
