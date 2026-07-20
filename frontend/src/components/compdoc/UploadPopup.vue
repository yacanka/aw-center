<template>
  <n-modal v-model:show="showModal" preset="dialog" title="Upload Excel" centered width="500px">
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

  <n-modal v-model:show="showPreviewModal" preset="card" title="Confirm Excel Import" width="900px">
    <n-alert type="info" :bordered="false">
      Header row {{ preview?.header_row }} was detected. Review mappings and validation warnings
      before saving.
    </n-alert>
    <n-space style="margin: 12px 0">
      <n-tag type="success">Create: {{ preview?.created_count || 0 }}</n-tag>
      <n-tag type="warning">Update: {{ preview?.updated_count || 0 }}</n-tag>
      <n-tag>Unchanged: {{ preview?.unchanged_count || 0 }}</n-tag>
      <n-tag :type="preview?.rejected_count ? 'error' : 'default'">
        Reject: {{ preview?.rejected_count || 0 }}
      </n-tag>
    </n-space>
    <n-data-table :columns="mappingColumns" :data="preview?.mapped_columns || []" size="small" />
    <n-alert v-if="preview?.missing_columns.length" type="error" style="margin-top: 12px">
      Missing required columns: {{ preview.missing_columns.join(', ') }}
    </n-alert>
    <n-alert v-if="preview?.unmapped_columns.length" type="warning" style="margin-top: 12px">
      Unmapped columns: {{ preview.unmapped_columns.join(', ') }}
    </n-alert>
    <n-data-table
      v-if="preview?.invalid_documents.length"
      :columns="validationColumns"
      :data="preview.invalid_documents"
      size="small"
      style="margin-top: 12px"
    />
    <template #footer>
      <n-space justify="end">
        <n-button @click="cancelPreview">Cancel</n-button>
        <n-button
          type="primary"
          :loading="confirmingImport"
          :disabled="Boolean(preview?.missing_columns.length)"
          @click="confirmImport"
          >Confirm Import</n-button
        >
      </n-space>
    </template>
  </n-modal>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import {
  NModal,
  NUpload,
  UploadCustomRequestOptions,
  NButton,
  NDataTable,
  NSpace,
  NAlert,
  NTag
} from 'naive-ui'
import type { DataTableColumns } from 'naive-ui'
import { useCompdocStore } from '@/stores/compdoc'
import { popupStore } from '@/stores/popupStore'
import { isPlainObject } from '@/utils/general'
import { formatApiError } from '@/services/apiError'
import {
  confirmCompdocImport,
  previewCompdocImport,
  type ImportInvalidDocument,
  type ImportMappingRow,
  type ImportPreview
} from '@/services/compdocImports'

const showModal = ref(false)
const showPreviewModal = ref(false)
const confirmingImport = ref(false)
const pendingFile = ref<File | null>(null)
const preview = ref<ImportPreview | null>(null)
const uploadCallbacks = ref<Pick<UploadCustomRequestOptions, 'onFinish' | 'onError'> | null>(null)
const store = useCompdocStore()
const popup = popupStore()
const mappingColumns: DataTableColumns<ImportMappingRow> = [
  { title: 'Excel Column', key: 'source' },
  { title: 'Mapped Model Field', key: 'target' }
]
const validationColumns: DataTableColumns<ImportInvalidDocument> = [
  { title: 'Row', key: 'row' },
  { title: 'Name', key: 'name' },
  { title: 'Validation Error', key: 'error_text' }
]

function setActive(show: boolean) {
  showModal.value = show
}

const props = defineProps<{
  uploadUrl: string
}>()

defineExpose({
  setActive
})

async function handleUploadReq(options: UploadCustomRequestOptions) {
  if (!options.file.file) return
  pendingFile.value = options.file.file
  uploadCallbacks.value = { onFinish: options.onFinish, onError: options.onError }
  await previewImport(options.file.file)
}

async function previewImport(file: File) {
  window.$loadingBar.start()
  try {
    preview.value = await previewCompdocImport(props.uploadUrl, file)
    showPreviewModal.value = true
    window.$loadingBar.finish()
  } catch (err: unknown) {
    uploadCallbacks.value?.onError()
    showUploadError(err)
  }
}

async function confirmImport() {
  if (!pendingFile.value || !preview.value?.confirmation_token) return
  confirmingImport.value = true
  window.$loadingBar.start()
  try {
    const result = await confirmCompdocImport(
      props.uploadUrl,
      pendingFile.value,
      preview.value.confirmation_token
    )
    window.$loadingBar.finish()
    uploadCallbacks.value?.onFinish()
    showUploadSuccess(result.message, result.invalid_documents)
  } catch (err: unknown) {
    uploadCallbacks.value?.onError()
    showUploadError(err)
  } finally {
    confirmingImport.value = false
    store.fetchCompdocs()
    resetUploadState()
  }
}

function cancelPreview() {
  uploadCallbacks.value?.onError()
  resetUploadState()
}

function showUploadSuccess(message: string, invalidDocuments?: ImportInvalidDocument[]) {
  window.$notification.success({ title: 'Success', description: message, duration: 3000 })
  if (invalidDocuments?.length) showInvalidDocuments(invalidDocuments)
}

function showUploadError(err: unknown) {
  window.$loadingBar.error()
  window.$notification.error({
    title: 'Error',
    description: `Error while uploading file: ${formatApiError(err)}`
  })
}

function showInvalidDocuments(invalidDocuments: ImportInvalidDocument[]) {
  const result = invalidDocuments.map(formatInvalidDocument).join('\n')
  popup.open('Some documents cannot be imported', result)
}

function formatInvalidDocument(document: ImportInvalidDocument) {
  const errorText = isPlainObject(document.error)
    ? Object.entries(document.error as Record<string, unknown>)
        .map(([key, value]) => `${key}: ${value}`)
        .join('\n')
    : String(document.error)
  const rowLabel = document.row ? `[Row] ${document.row}\n` : ''
  return `${rowLabel}[Name] ${document.name}\n[Error] ${document.error_text || errorText}\n`
}

function resetUploadState() {
  pendingFile.value = null
  preview.value = null
  uploadCallbacks.value = null
  showPreviewModal.value = false
  setActive(false)
}
</script>

<style scoped></style>
