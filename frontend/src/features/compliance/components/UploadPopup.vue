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

  <n-modal
    :show="showPreviewModal"
    :mask-closable="!busy"
    :close-on-esc="!busy"
    :closable="!busy"
    @update:show="
      (show: boolean) => {
        if (!show) cancelPreview()
      }
    "
    preset="card"
    title="Confirm Excel Import"
    class="app-modal app-modal--large"
  >
    <n-tabs v-model:value="mode" type="line" style="margin-bottom: 16px">
      <n-tab name="automatic" :disabled="busy">Automatic linking</n-tab>
      <n-tab name="manual" :disabled="busy">Manual linking</n-tab>
    </n-tabs>
    <n-alert type="info" :bordered="false">
      Header row {{ source?.header_row }} was detected. Review mappings and validation warnings
      before saving. This preview is protected against concurrent database changes.
    </n-alert>
    <n-alert v-if="previewNotice" type="warning" style="margin-top: 12px">
      {{ previewNotice }}
    </n-alert>
    <div v-if="mode === 'manual'" style="margin-top: 16px">
      <n-p
        >Link Excel columns to document fields. Unlinked columns will be ignored. Name is
        required.</n-p
      >
      <n-form-item v-for="column in source?.source_columns || []" :key="column" :label="column">
        <n-select
          :value="mapping[column] || null"
          :options="fieldOptions(column)"
          :disabled="busy"
          clearable
          filterable
          placeholder="Do not import"
          @update:value="(value: string | null) => updateMapping(column, value)"
        />
      </n-form-item>
    </div>
    <template v-if="preview">
      <n-space style="margin: 12px 0">
        <n-tag type="success">Create: {{ preview?.created_count || 0 }}</n-tag>
        <n-tag type="warning">Update: {{ preview?.updated_count || 0 }}</n-tag>
        <n-tag>Unchanged: {{ preview?.unchanged_count || 0 }}</n-tag>
        <n-tag :type="preview?.rejected_count ? 'error' : 'default'">
          Reject: {{ preview?.rejected_count || 0 }}
        </n-tag>
      </n-space>
      <n-data-table
        :columns="mappingColumns"
        :data="preview?.mapped_columns || []"
        :scroll-x="520"
        size="small"
      />
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
        :scroll-x="760"
        size="small"
        style="margin-top: 12px"
      />
    </template>
    <template #footer>
      <n-space justify="end">
        <n-button :disabled="busy" @click="cancelPreview">Cancel</n-button>
        <n-button :loading="validating" :disabled="busy" @click="validateImport"
          >Validate import</n-button
        >
        <n-button
          type="primary"
          :loading="confirmingImport"
          :disabled="!canConfirm"
          @click="confirmImport"
          >Confirm Import</n-button
        >
      </n-space>
    </template>
  </n-modal>
</template>

<script setup lang="ts">
import {
  NModal,
  NUpload,
  NButton,
  NDataTable,
  NSpace,
  NAlert,
  NTag,
  NTabs,
  NTab,
  NSelect,
  NFormItem,
  NP
} from 'naive-ui'
import type { DataTableColumns } from 'naive-ui'
import type {
  ImportInvalidDocument,
  ImportMappingRow
} from '@/features/compliance/api/compdocImports'
import { useCompdocImport } from '@/features/compliance/composables/useCompdocImport'
const mappingColumns: DataTableColumns<ImportMappingRow> = [
  { title: 'Excel Column', key: 'source', minWidth: 240 },
  { title: 'Mapped Model Field', key: 'target', minWidth: 280 }
]
const validationColumns: DataTableColumns<ImportInvalidDocument> = [
  { title: 'Row', key: 'row', width: 80 },
  { title: 'Name', key: 'name', minWidth: 240 },
  {
    title: 'Validation Error',
    key: 'fields',
    minWidth: 440,
    render: (row) =>
      Object.entries(row.fields || {})
        .map(([field, value]) => `${field}: ${Array.isArray(value) ? value.join(', ') : value}`)
        .join(' · ')
  }
]

const props = defineProps<{
  uploadUrl: string
}>()

const {
  mode,
  mapping,
  source,
  validating,
  busy,
  canConfirm,
  validateImport,
  showModal,
  showPreviewModal,
  confirmingImport,
  previewNotice,
  preview,
  setActive,
  handleUploadReq,
  confirmImport,
  cancelPreview
} = useCompdocImport(() => props.uploadUrl)

function fieldOptions(column: string) {
  return (source.value?.target_fields || []).map((field) => ({
    label: `${field.label}${field.required ? ' (required)' : ''}`,
    value: field.key,
    disabled: Object.entries(mapping.value).some(
      ([sourceColumn, target]) => sourceColumn !== column && target === field.key
    )
  }))
}

function updateMapping(column: string, value: string | null) {
  const next = { ...mapping.value }
  if (value) next[column] = value
  else delete next[column]
  mapping.value = next
}

defineExpose({
  setActive
})
</script>

<style scoped></style>
