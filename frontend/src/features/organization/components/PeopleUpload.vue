<template>
  <n-modal
    v-model:show="showModal"
    preset="dialog"
    title="Upload Excel"
    centered
    class="app-modal app-modal--small"
  >
    <div class="modal-content">
      <n-upload
        directory-dnd
        :show-file-list="false"
        :max="1"
        accept=".xlsm,.xlsx"
        :custom-request="handleUploadReq"
      >
        <n-upload-dragger>
          <n-text style="font-size: 16px"> Click or drag a file to this area to upload </n-text>
          <n-p depth="3" style="margin: 8px 0 0 0"> Upload compliance document Excel file </n-p>
        </n-upload-dragger>
      </n-upload>
    </div>
  </n-modal>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { NModal, NUpload, UploadCustomRequestOptions } from 'naive-ui'
import { useOrganizationController } from '@/features/organization/composables/organizationController'
import { popupStore } from '@/app/stores/popupStore'

const showModal = ref(false)
const store = useOrganizationController()
const popup = popupStore()

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
    if (res.rejected.length) {
      const result = res.rejected
        .map((person) => {
          const errors = Object.entries(person.errors)
            .map(
              ([field, value]) =>
                `${field}: ${Array.isArray(value) ? value.join(', ') : String(value)}`
            )
            .join('\n')
          return `[Row] ${person.row}\n[Error] ${errors}`
        })
        .join('\n\n')
      popup.open('Some people could not be imported', result)
    }
    await store.fetchPeople(true)
    window.$loadingBar.finish()
  } catch (e) {
    window.$loadingBar.error()
  } finally {
    closeModal()
  }
}
</script>

<style scoped></style>
