<script setup lang="ts">
import { computed, h, onMounted, ref } from 'vue'
import { NButton, NTag, type DataTableColumns, type PaginationInfo } from 'naive-ui'
import type { IDcc } from '@/features/dcc/models/dcc'
import { fetchDccRecords } from '@/features/dcc/api/dccRecords'
import type { PaginationMeta } from '@/shared/services/pagination'

const records = ref<IDcc[]>([])
const loading = ref(false)
const pageMeta = ref<PaginationMeta>({ count: 0, next: null, previous: null })
const page = ref(1)
const pageSize = ref(12)
const pagination = computed<Partial<PaginationInfo>>(() => ({
  page: page.value,
  pageSize: pageSize.value,
  itemCount: pageMeta.value.count,
  showSizePicker: true,
  pageSizes: [12, 25, 50, 100]
}))

const columns: DataTableColumns<IDcc> = [
  { title: 'Issue', key: 'issue', width: 140 },
  { title: 'Title', key: 'title', minWidth: 260, ellipsis: { tooltip: true } },
  {
    title: 'State',
    key: 'active',
    width: 110,
    render: (row) =>
      h(NTag, { type: row.active ? 'success' : 'default', bordered: false }, () =>
        row.active ? 'Active' : 'Inactive'
      )
  },
  {
    title: 'JIRA',
    key: 'jira_issue_url',
    width: 110,
    render: (row) =>
      h(
        NButton,
        {
          text: true,
          type: 'primary',
          disabled: !row.jira_issue_url,
          onClick: () => openJiraIssue(row.jira_issue_url)
        },
        () => 'Open issue'
      )
  }
]

async function fetchDcc(): Promise<void> {
  loading.value = true
  try {
    const result = await fetchDccRecords({ page: page.value, page_size: pageSize.value })
    records.value = result.results
    pageMeta.value = result.pagination
  } catch {
    records.value = []
    window.$message.error('DCC records could not be loaded.')
  } finally {
    loading.value = false
  }
}

function handlePageUpdate(newPage: number): void {
  page.value = newPage
  void fetchDcc()
}

function handlePageSizeUpdate(newPageSize: number): void {
  pageSize.value = newPageSize
  page.value = 1
  void fetchDcc()
}

function openJiraIssue(url?: string): void {
  if (!url) return
  window.open(url, '_blank', 'noopener,noreferrer')
}

onMounted(fetchDcc)
</script>

<template>
  <n-card title="DCC records">
    <n-alert type="info" :bordered="false" style="margin-bottom: 12px">
      This view shows the bounded DCC register. JIRA synchronization, reminder email, direct ECD
      upload, and legacy assessment actions are unavailable in the current API.
    </n-alert>
    <n-flex justify="end">
      <n-text><strong>Total:</strong> {{ pageMeta.count }}</n-text>
    </n-flex>
    <n-data-table
      :loading="loading"
      :columns="columns"
      :data="records"
      :pagination="pagination"
      :row-key="(row: IDcc) => row.id"
      :scroll-x="620"
      remote
      striped
      size="small"
      @update:page="handlePageUpdate"
      @update:page-size="handlePageSizeUpdate"
    />
  </n-card>
</template>
