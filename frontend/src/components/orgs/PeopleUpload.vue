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
import { useOrgsStore } from '@/stores/api'
import { popupStore } from '@/stores/popupStore';
import { isPlainObject } from '@/utils/general';

const showModal = ref(false);
const store = useOrgsStore()
const popup = popupStore()

onMounted(() => {

});

function openModal() {
  showModal.value = true
}

function closeModal() {
  showModal.value = false
}

defineExpose({
  openModal
})

async function handleUploadReq({ file }: UploadCustomRequestOptions) {
  if (!file.file) return

  const formData = new FormData()
  formData.append('file', file.file)
  
  window.$loadingBar.start()
  try {
    const res = await store.uploadPeople(formData)
    if (res.error_list) {
      let result = ""
      const error_list = res.error_list
      error_list.forEach((person: any) => {
        let errorText = ""
        if (isPlainObject(person.error)) {
          errorText = Object.entries(person.error).map(([key, value]) => `${key}: ${value}`).join("\n");
        } else {
          errorText = person.error
        }
        result += `[Name] ${person.name}\n[Error] ${errorText}\n\n`
      })
      popup.open("Some person cannot be imported", result)
    }
    store.fetchPeople()
    window.$loadingBar.finish()
  } catch (e) {
    window.$loadingBar.error()
  } finally {
    closeModal()
  }
}

</script>

<style scoped></style>
