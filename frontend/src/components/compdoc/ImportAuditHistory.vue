<template>
  <n-button v-if="allowed" secondary @click="openModal">Import history</n-button>
  <n-modal v-model:show="show" preset="card" title="CompDoc import history" :style="modalStyle">
    <n-space align="center" style="margin-bottom: 16px">
      <n-input
        v-model:value="search"
        clearable
        placeholder="Search filename or importer"
        @keyup.enter="fetchFirstPage"
      />
      <n-select
        v-model:value="selectedStatus"
        clearable
        placeholder="All statuses"
        :options="statusOptions"
      />
      <n-button :loading="loading" @click="fetchFirstPage">Search</n-button>
    </n-space>
    <n-data-table
      remote
      striped
      :loading="loading"
      :columns="columns"
      :data="audits"
      :pagination="pagination"
      :row-key="(row: ImportAudit) => row.id"
      @update:page="updatePage"
      @update:page-size="updatePageSize"
    />
  </n-modal>
  <ImportAuditDetail ref="detail" />
</template>

<script setup lang="ts">
import { computed, h, ref } from 'vue'
import { NButton, NTag, type DataTableColumns, type PaginationInfo } from 'naive-ui'
import ImportAuditDetail from '@/components/compdoc/ImportAuditDetail.vue'
import { formatApiError } from '@/services/apiError'
import {
  listImportAudits,
  type ImportAudit,
  type ImportAuditStatus
} from '@/services/compdocImportAudits'

const props = defineProps<{ allowed: boolean; project: string }>()
const modalStyle = { width: 'min(1180px, 94vw)' }
const statusOptions = ['processing', 'success', 'partial', 'failed'].map((value) => ({
  label: titleCase(value),
  value
}))
const statusTypes = {
  processing: 'info',
  success: 'success',
  partial: 'warning',
  failed: 'error'
} as const
const show = ref(false)
const loading = ref(false)
const audits = ref<ImportAudit[]>([])
const search = ref('')
const selectedStatus = ref<ImportAuditStatus | null>(null)
const page = ref(1)
const pageSize = ref(12)
const count = ref(0)
const detail = ref<InstanceType<typeof ImportAuditDetail> | null>(null)
const pagination = computed<Partial<PaginationInfo>>(() => ({
  page: page.value,
  pageSize: pageSize.value,
  itemCount: count.value,
  showSizePicker: true,
  pageSizes: [12, 25, 50, 100]
}))
const columns: DataTableColumns<ImportAudit> = [
  { title: 'File', key: 'source_filename', ellipsis: { tooltip: true } },
  { title: 'Imported by', key: 'imported_by_username' },
  {
    title: 'Status',
    key: 'status',
    render: (row) => h(NTag, { type: statusTypes[row.status] }, () => titleCase(row.status))
  },
  { title: 'Rows', key: 'total_rows', width: 70 },
  {
    title: 'Created / Updated / Rejected',
    key: 'result',
    render: (row) => `${row.created_count} / ${row.updated_count} / ${row.rejected_count}`
  },
  { title: 'Started', key: 'started_at', render: (row) => formatDate(row.started_at) },
  {
    title: '',
    key: 'actions',
    render: (row) =>
      h(NButton, { size: 'small', onClick: () => detail.value?.open(row.id) }, () => 'Details')
  }
]

function openModal(): void {
  show.value = true
  fetchFirstPage()
}

function fetchFirstPage(): void {
  page.value = 1
  void fetchAudits()
}

async function fetchAudits(): Promise<void> {
  loading.value = true
  try {
    const result = await listImportAudits({
      project: props.project,
      page: page.value,
      page_size: pageSize.value,
      search: search.value.trim() || undefined,
      status: selectedStatus.value || undefined
    })
    audits.value = result.results
    count.value = result.count
  } catch (error) {
    window.$message.error(formatApiError(error))
  } finally {
    loading.value = false
  }
}

function updatePage(value: number): void {
  page.value = value
  void fetchAudits()
}

function updatePageSize(value: number): void {
  pageSize.value = value
  fetchFirstPage()
}

function formatDate(value: string): string {
  return new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(
    new Date(value)
  )
}

function titleCase(value: string): string {
  return value.charAt(0).toUpperCase() + value.slice(1)
}
</script>
