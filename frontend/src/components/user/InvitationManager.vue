<template>
  <n-button v-if="allowed" secondary type="primary" @click="openModal">Manage invitations</n-button>
  <n-modal
    v-model:show="show"
    preset="card"
    title="Invitation activity"
    :style="modalStyle"
    :bordered="false"
  >
    <n-space align="center" style="margin-bottom: 16px">
      <n-input
        v-model:value="search"
        clearable
        placeholder="Search email or username"
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
      :data="invitations"
      :pagination="pagination"
      :row-key="(row: ManagedInvitation) => row.id"
      @update:page="updatePage"
      @update:page-size="updatePageSize"
    >
      <template #empty>
        <n-empty description="No invitations found." />
      </template>
    </n-data-table>
  </n-modal>
</template>

<script setup lang="ts">
import { computed, h, ref } from 'vue'
import { NButton, NTag, type DataTableColumns, type PaginationInfo } from 'naive-ui'
import { formatApiError } from '@/services/apiError'
import {
  listUserInvitations,
  revokeUserInvitation,
  type InvitationStatus,
  type ManagedInvitation
} from '@/services/userInvitations'

defineProps<{ allowed: boolean }>()
const modalStyle = { width: 'min(1180px, 94vw)' }
const statusOptions = [
  { label: 'Active', value: 'active' },
  { label: 'Used', value: 'used' },
  { label: 'Expired', value: 'expired' },
  { label: 'Revoked', value: 'revoked' }
]
const statusTypes = {
  active: 'success',
  used: 'info',
  expired: 'warning',
  revoked: 'error'
} as const
const show = ref(false)
const loading = ref(false)
const invitations = ref<ManagedInvitation[]>([])
const search = ref('')
const selectedStatus = ref<InvitationStatus | null>(null)
const page = ref(1)
const pageSize = ref(12)
const count = ref(0)
const pagination = computed<Partial<PaginationInfo>>(() => ({
  page: page.value,
  pageSize: pageSize.value,
  itemCount: count.value,
  showSizePicker: true,
  pageSizes: [12, 25, 50, 100]
}))

const columns: DataTableColumns<ManagedInvitation> = [
  { title: 'Email', key: 'email', ellipsis: { tooltip: true } },
  {
    title: 'Status',
    key: 'status',
    render: (row) => h(NTag, { type: statusTypes[row.status] }, () => titleCase(row.status))
  },
  {
    title: 'Groups',
    key: 'groups',
    render: (row) => row.groups.join(', ') || 'None',
    ellipsis: { tooltip: true }
  },
  { title: 'Created by', key: 'created_by', render: (row) => row.created_by || 'Deleted user' },
  { title: 'Created', key: 'created_at', render: (row) => formatDate(row.created_at) },
  { title: 'Expires', key: 'expires_at', render: (row) => formatDate(row.expires_at) },
  { title: 'Used by', key: 'used_by', render: (row) => row.used_by || '—' },
  {
    title: '',
    key: 'actions',
    render: (row) =>
      h(
        NButton,
        {
          size: 'small',
          type: 'error',
          disabled: row.status !== 'active',
          onClick: () => confirmRevoke(row)
        },
        () => 'Revoke'
      )
  }
]

function openModal(): void {
  show.value = true
  page.value = 1
  void fetchInvitations()
}

function fetchFirstPage(): void {
  page.value = 1
  void fetchInvitations()
}

async function fetchInvitations(): Promise<void> {
  loading.value = true
  try {
    const response = await listUserInvitations(buildFilters())
    invitations.value = response.results
    count.value = response.count
  } catch (error) {
    window.$message.error(formatApiError(error))
  } finally {
    loading.value = false
  }
}

function buildFilters() {
  return {
    page: page.value,
    page_size: pageSize.value,
    search: search.value.trim() || undefined,
    status: selectedStatus.value || undefined
  }
}

function updatePage(nextPage: number): void {
  page.value = nextPage
  void fetchInvitations()
}

function updatePageSize(nextPageSize: number): void {
  pageSize.value = nextPageSize
  page.value = 1
  void fetchInvitations()
}

function confirmRevoke(invitation: ManagedInvitation): void {
  window.$dialog.warning({
    title: 'Revoke invitation',
    content: `Immediately invalidate the invitation for ${invitation.email}?`,
    positiveText: 'Revoke',
    negativeText: 'Keep active',
    onPositiveClick: () => performRevoke(invitation.id)
  })
}

async function performRevoke(invitationId: number): Promise<void> {
  try {
    await revokeUserInvitation(invitationId)
    window.$message.success('Invitation revoked.')
    await fetchInvitations()
  } catch (error) {
    window.$message.error(formatApiError(error))
  }
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
