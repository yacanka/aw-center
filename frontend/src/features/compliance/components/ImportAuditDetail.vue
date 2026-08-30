<template>
  <n-modal
    v-model:show="show"
    preset="card"
    title="Import audit details"
    class="app-modal app-modal--large"
  >
    <n-spin :show="loading">
      <n-descriptions v-if="audit" bordered :column="isNarrow ? 1 : 3" label-placement="top">
        <n-descriptions-item label="File">{{ audit.source_filename }}</n-descriptions-item>
        <n-descriptions-item label="Importer ID">{{ audit.imported_by }}</n-descriptions-item>
        <n-descriptions-item label="Status">{{ titleCase(audit.status) }}</n-descriptions-item>
        <n-descriptions-item label="Rows">{{ audit.total_rows }}</n-descriptions-item>
        <n-descriptions-item label="Result">
          +{{ audit.created_count }} / ~{{ audit.updated_count }} / ={{ audit.unchanged_count }} /
          !{{ audit.rejected_count }}
        </n-descriptions-item>
        <n-descriptions-item label="Duration">{{
          formatDuration(audit.duration_ms)
        }}</n-descriptions-item>
        <n-descriptions-item label="SHA-256" :span="3">
          <n-text code>{{ audit.source_sha256 }}</n-text>
        </n-descriptions-item>
        <n-descriptions-item label="Request reference" :span="3">
          {{ audit.request_id || '—' }}
        </n-descriptions-item>
      </n-descriptions>
      <n-divider v-if="audit" title-placement="left">Detected mappings</n-divider>
      <n-data-table
        v-if="audit"
        size="small"
        :columns="mappingColumns"
        :data="audit.mapped_columns"
        :pagination="false"
        :scroll-x="520"
      />
      <n-alert v-if="audit?.missing_columns.length" type="error" class="detail-alert">
        Missing columns: {{ audit.missing_columns.join(', ') }}
      </n-alert>
      <n-alert v-if="audit?.unmapped_columns.length" type="warning" class="detail-alert">
        Unmapped columns: {{ audit.unmapped_columns.join(', ') }}
      </n-alert>
      <n-divider v-if="audit?.error_summary.length" title-placement="left">Rejected rows</n-divider>
      <n-data-table
        v-if="audit?.error_summary.length"
        size="small"
        :columns="errorColumns"
        :data="audit.error_summary"
        :pagination="false"
        :scroll-x="920"
      />
    </n-spin>
  </n-modal>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import type { DataTableColumns } from 'naive-ui'
import { formatApiError } from '@/shared/api/apiError'
import { useMediaQuery } from '@/shared/composables/mediaQuery'
import {
  getImportAudit,
  type ImportAuditDetail,
  type ImportAuditError
} from '@/features/compliance/api/compdocImportAudits'

const props = defineProps<{ project: string }>()
const isNarrow = useMediaQuery('(max-width: 700px)')
const show = ref(false)
const loading = ref(false)
const audit = ref<ImportAuditDetail | null>(null)
const mappingColumns = [
  { title: 'Source column', key: 'source', minWidth: 240 },
  { title: 'Model field', key: 'target', minWidth: 280 }
]
const errorColumns: DataTableColumns<ImportAuditError> = [
  { title: 'Row', key: 'row', width: 70 },
  { title: 'Document', key: 'name', minWidth: 240, ellipsis: { tooltip: true } },
  { title: 'Code', key: 'code', width: 190 },
  { title: 'Detail', key: 'detail', minWidth: 420, ellipsis: { tooltip: true } }
]

async function open(auditId: string): Promise<void> {
  show.value = true
  loading.value = true
  audit.value = null
  try {
    audit.value = await getImportAudit(props.project, auditId)
  } catch (error) {
    window.$message.error(formatApiError(error))
  } finally {
    loading.value = false
  }
}

function formatDuration(duration: number | null): string {
  return duration === null ? '—' : `${duration.toLocaleString()} ms`
}

function titleCase(value: string): string {
  return value.charAt(0).toUpperCase() + value.slice(1)
}

defineExpose({ open })
</script>

<style scoped>
.detail-alert {
  margin-top: 12px;
}
</style>
