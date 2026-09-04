<template>
  <n-modal
    v-model:show="showUpload"
    preset="dialog"
    title="Import Panels from Excel"
    centered
    class="app-modal app-modal--small"
  >
    <n-upload
      directory-dnd
      :show-file-list="false"
      :max="1"
      accept=".xlsm,.xlsx"
      :custom-request="handleUpload"
    >
      <n-upload-dragger>
        <n-text style="font-size: 16px">Click or drag a workbook here</n-text>
        <n-p depth="3" style="margin: 8px 0 0">
          Only Panel and ATA Chapter columns are imported. One panel may contain multiple ATA values
          separated by commas, semicolons, or new lines.
        </n-p>
      </n-upload-dragger>
    </n-upload>
  </n-modal>

  <n-modal
    v-model:show="showPreview"
    preset="card"
    title="Confirm Panel Import"
    class="app-modal app-modal--large"
  >
    <n-alert type="info" :bordered="false">
      Header row {{ preview?.header_row }} was detected. Existing project panels are matched by
      unique ATA Chapter; their names will be updated and disciplines will be preserved.
    </n-alert>
    <n-alert v-if="previewNotice" type="warning" style="margin-top: 12px">
      {{ previewNotice }}
    </n-alert>
    <n-space style="margin: 12px 0">
      <n-tag type="success">Create: {{ preview?.created_count ?? 0 }}</n-tag>
      <n-tag type="warning">Update: {{ preview?.updated_count ?? 0 }}</n-tag>
      <n-tag>Unchanged: {{ preview?.unchanged_count ?? 0 }}</n-tag>
      <n-tag :type="preview?.rejected_count ? 'error' : 'default'">
        Reject: {{ preview?.rejected_count ?? 0 }}
      </n-tag>
    </n-space>

    <n-data-table
      :columns="mappingColumns"
      :data="preview?.mapped_columns ?? []"
      :scroll-x="520"
      size="small"
    />
    <n-alert v-if="preview?.unmapped_columns.length" type="warning" style="margin-top: 12px">
      Ignored columns: {{ preview.unmapped_columns.join(', ') }}
    </n-alert>
    <n-data-table
      v-if="invalidRows.length"
      :columns="validationColumns"
      :data="invalidRows"
      :scroll-x="720"
      size="small"
      style="margin-top: 12px"
    />

    <template #footer>
      <n-space justify="end">
        <n-button @click="cancelPreview">Cancel</n-button>
        <n-button type="primary" :loading="confirming" @click="confirmImport">
          Confirm Import
        </n-button>
      </n-space>
    </template>
  </n-modal>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import type { DataTableColumns, UploadCustomRequestOptions } from 'naive-ui'
import {
  confirmPanelImport,
  previewPanelImport,
  type InvalidPanelImportRow,
  type PanelImportMapping,
  type PanelImportPreview
} from '@/features/organization/api/organizationPanelImports'
import { useOrganizationController } from '@/features/organization/composables/organizationController'
import { formatApiError, getApiErrorCode } from '@/shared/api/apiError'

type ValidationRow = InvalidPanelImportRow & { error_text: string }

const REFRESHABLE_CODES = new Set(['PANEL_IMPORT_VERSION_CONFLICT', 'PANEL_IMPORT_PREVIEW_EXPIRED'])
const store = useOrganizationController()
const showUpload = ref(false)
const showPreview = ref(false)
const confirming = ref(false)
const previewNotice = ref('')
const pendingFile = ref<File | null>(null)
const preview = ref<PanelImportPreview | null>(null)
const callbacks = ref<Pick<UploadCustomRequestOptions, 'onFinish' | 'onError'> | null>(null)

const mappingColumns: DataTableColumns<PanelImportMapping> = [
  { title: 'Excel Column', key: 'source', minWidth: 240 },
  { title: 'Mapped Field', key: 'target', minWidth: 240 }
]
const validationColumns: DataTableColumns<ValidationRow> = [
  { title: 'Row', key: 'row', width: 80 },
  { title: 'Code', key: 'code', width: 210 },
  { title: 'Validation Error', key: 'error_text', minWidth: 400 }
]
const invalidRows = computed<ValidationRow[]>(() =>
  (preview.value?.invalid_panels ?? []).map((row) => ({
    ...row,
    error_text: Object.entries(row.fields)
      .map(([field, value]) => `${field}: ${String(value)}`)
      .join('\n')
  }))
)

function openModal(): void {
  showUpload.value = true
}

async function handleUpload(options: UploadCustomRequestOptions): Promise<void> {
  if (!options.file.file || !store.project) return
  pendingFile.value = options.file.file
  callbacks.value = { onFinish: options.onFinish, onError: options.onError }
  await loadPreview(options.file.file)
}

async function loadPreview(file: File, refreshed = false): Promise<void> {
  window.$loadingBar.start()
  try {
    preview.value = await previewPanelImport(store.project, file)
    previewNotice.value = refreshed
      ? 'Panel records changed after review. The preview was refreshed; review it again.'
      : ''
    showPreview.value = true
    window.$loadingBar.finish()
  } catch (error: unknown) {
    callbacks.value?.onError()
    showError(error)
  }
}

async function confirmImport(): Promise<void> {
  if (!pendingFile.value || !preview.value?.confirmation_token || !store.project) return
  confirming.value = true
  window.$loadingBar.start()
  try {
    const result = await confirmPanelImport(
      store.project,
      pendingFile.value,
      preview.value.confirmation_token
    )
    await store.fetchPanels()
    callbacks.value?.onFinish()
    window.$loadingBar.finish()
    window.$notification.success({
      title: 'Panel import completed',
      description: `${result.created_count} created, ${result.updated_count} updated, ${result.rejected_count} rejected.`,
      duration: 4000
    })
    reset()
  } catch (error: unknown) {
    if (pendingFile.value && REFRESHABLE_CODES.has(getApiErrorCode(error) ?? '')) {
      await loadPreview(pendingFile.value, true)
    } else {
      callbacks.value?.onError()
      showError(error)
    }
  } finally {
    confirming.value = false
  }
}

function cancelPreview(): void {
  callbacks.value?.onError()
  reset()
}

function reset(): void {
  showUpload.value = false
  showPreview.value = false
  pendingFile.value = null
  preview.value = null
  previewNotice.value = ''
  callbacks.value = null
}

function showError(error: unknown): void {
  window.$loadingBar.error()
  window.$notification.error({
    title: 'Panel import failed',
    description: formatApiError(error)
  })
}

defineExpose({ openModal })
</script>
