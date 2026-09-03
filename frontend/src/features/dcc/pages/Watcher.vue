<script setup lang="ts">
import { computed, h, onMounted, ref } from 'vue'
import { NButton, NFlex, NTag, type DataTableColumns, type PaginationInfo } from 'naive-ui'
import type { IDcc } from '@/features/dcc/models/dcc'
import { fetchDccRecords } from '@/features/dcc/api/dccRecords'
import type { PaginationMeta } from '@/shared/services/pagination'
import DccReminderDialog from '@/features/dcc/components/DccReminderDialog.vue'
import { useProjectCatalogStore } from '@/features/projects/stores/projectCatalog'
import { hasProjectDccRole } from '@/features/projects/models/projectRegistry'

const records = ref<IDcc[]>([])
const loading = ref(false)
const pageMeta = ref<PaginationMeta>({ count: 0, next: null, previous: null })
const page = ref(1)
const pageSize = ref(12)
const reminderDialog = ref<InstanceType<typeof DccReminderDialog> | null>(null)
const projectCatalog = useProjectCatalogStore()
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
    title: 'Actions',
    key: 'actions',
    width: 230,
    render: (row) =>
      h(NFlex, { wrap: false, size: 'small' }, () => [
        h(
          NButton,
          {
            text: true,
            type: 'primary',
            disabled: !row.jira_issue_url,
            onClick: () => openJiraIssue(row.jira_issue_url)
          },
          () => 'Open issue'
        ),
        h(
          NButton,
          {
            size: 'small',
            type: 'info',
            ghost: true,
            disabled: !row.active || !canSendReminder(row),
            onClick: () => reminderDialog.value?.open(row)
          },
          () => 'Send reminder'
        )
      ])
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

function canSendReminder(row: IDcc): boolean {
  if (projectCatalog.status !== 'ready' || row.project_slugs.length === 0) return false
  return row.project_slugs.every((slug) => {
    const project = projectCatalog.projects.find((item) => item.slug === slug)
    return Boolean(project && hasProjectDccRole(project.roles.dcc, 'operator'))
  })
}

onMounted(fetchDcc)
</script>

<template>
  <n-card title="DCC records">
    <n-alert type="info" :bordered="false" style="margin-bottom: 12px">
      This view shows the bounded DCC register. Reminder recipients are resolved from open JIRA
      subtasks and delivery is handled by the notification worker.
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
      :scroll-x="760"
      remote
      striped
      size="small"
      @update:page="handlePageUpdate"
      @update:page-size="handlePageSizeUpdate"
    />
    <DccReminderDialog ref="reminderDialog" />
  </n-card>
</template>
