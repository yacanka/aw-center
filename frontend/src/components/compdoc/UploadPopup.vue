<template>
  <n-modal v-model:show="showModal" preset="dialog" title="Upload Excel" centered width="500px">
    <div class="modal-content">
      <n-upload directory-dnd :show-file-list="false" :max="1" accept=".xlsm,.xlsx" :custom-request="handleUploadReq">
        <n-upload-dragger>
          <n-text style="font-size: 16px">
            Click or drag a file to this area to upload
          </n-text>
          <n-p depth="3" style="margin: 8px 0 0 0">
            Upload compliance document Excel file
          </n-p>
        </n-upload-dragger>
      </n-upload>
    </div>
  </n-modal>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { NModal, NUpload, UploadCustomRequestOptions } from 'naive-ui';
import axios from 'axios'
import { useCompdocStore } from '@/stores/api'
import { popupStore } from '@/stores/popupStore';
import { isPlainObject } from '@/utils/general';
import { InvalidDocument } from '@/models/compdocs'

const showModal = ref(false);
const store = useCompdocStore()
const popup = popupStore()

onMounted(() => {

});

function setActive(show: boolean) {
  showModal.value = show
}

const props = defineProps<{
  uploadUrl: string
}>()

defineExpose({
  setActive
})

async function handleUploadReq({ file, onFinish, onError }: UploadCustomRequestOptions) {
  if (!file.file) return
  const formData = new FormData()
  formData.append('file', file.file)

  window.$loadingBar.start()
  try {
    const res = await axios.post(props.uploadUrl, formData)
    window.$loadingBar.finish()
    window.$notification.success({
      title: 'Success',
      description: res.data.message,
      duration: 3000
    })
    if (res.data.invalid_documents) {
      let result = ""
      const invalid_documents = res.data.invalid_documents
      invalid_documents.forEach((document: InvalidDocument) => {
        let errorText = ""
        if (isPlainObject(document.error)) {
          errorText = Object.entries(document.error).map(([key, value]) => `${key}: ${value}`).join("\n");
        } else {
          errorText = document.error
        }
        result += `[Name] ${document.name}\n[Error] ${errorText}\n\n`
      })
      popup.open("Some documents cannot be imported", result)
    }
  } catch (err: any) {
    window.$loadingBar.error()
    window.$notification.error({
      title: 'Error',
      description: `Error while uploading file: ${err.response.data.message}`,
    })
  } finally {
    store.fetchCompdocs()
    setActive(false)
  }
}

</script>

<style scoped></style>
