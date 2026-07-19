<script setup lang="ts">
import { computed, h, ref, onMounted, onUnmounted } from 'vue'
import { DataTableColumns, PaginationInfo } from 'naive-ui'
import { useAuthStore } from '@/stores/api'
import { IUser, IPermission } from '@/models/auth'
import UpdateForm from '@/components/user/UserPopup.vue'
import Details from '@/components/user/DetailedInfo.vue'
import Unauthorized from '@/views/Unauthorized.vue'
import { useUserStore } from '@/stores/user'
import { isoToTurkishDateTime } from '@/utils/time'
import { getStringFilterFunc, getStringFilterMenuFunc } from '@/stores/datatable'
import InvitationLinkCreator from '@/components/user/InvitationLinkCreator.vue'
import InvitationManager from '@/components/user/InvitationManager.vue'
import { userActionColumn } from '@/services/userTableColumns'

const store = useAuthStore()
const userStore = useUserStore()
const page = ref(1)
const pageSize = ref(12)

const pagination = computed<Partial<PaginationInfo>>(() => ({
  page: page.value,
  pageSize: pageSize.value,
  itemCount: store.usersPagination.count,
  showSizePicker: true,
  pageSizes: [12, 25, 50, 100]
}))

const popupComponent = ref()
const filterValue = ref<Record<string, any>>({} as IUser)
const hasPermission = computed(() => hasEffectivePermission('view_user'))
const canInvite = computed(
  () =>
    Boolean(userStore.getUser.is_superuser) ||
    Boolean(userStore.getUser.is_staff && hasEffectivePermission('add_user'))
)
const canAccessPage = computed(() => hasPermission.value || canInvite.value)

function hasEffectivePermission(codename: string): boolean {
  return userStore.hasEffectiveRole('auth', codename)
}

const onFilter = (attrib: string, filterData: any) => {
  filterValue.value[attrib] = filterData
  page.value = 1
  fetchUsers()
}

const columns: DataTableColumns<IUser> = [
  {
    type: 'expand',
    expandable: (row) => true,
    renderExpand: (row) => {
      return h(Details, { user: row })
    },
    width: 1
  },
  {
    title: 'Username',
    key: 'username',
    width: 6,
    renderFilterMenu: getStringFilterMenuFunc('username', filterValue, onFilter),
    filter: getStringFilterFunc('username')
  },
  {
    title: 'Email',
    key: 'email',
    width: 12,
    renderFilterMenu: getStringFilterMenuFunc('email', filterValue, onFilter),
    filter: getStringFilterFunc('email'),
    ellipsis: {
      tooltip: true
    }
  },
  {
    title: 'First Name',
    key: 'first_name',
    width: 8,
    renderFilterMenu: getStringFilterMenuFunc('first_name', filterValue, onFilter),
    filter: getStringFilterFunc('first_name'),
    ellipsis: {
      tooltip: true
    }
  },
  {
    title: 'Last Name',
    key: 'last_name',
    width: 8,
    renderFilterMenu: getStringFilterMenuFunc('last_name', filterValue, onFilter),
    filter: getStringFilterFunc('last_name'),
    ellipsis: {
      tooltip: true
    }
  },
  {
    title: 'Last Login',
    key: 'last_login',
    width: 8,
    renderFilterMenu: getStringFilterMenuFunc('last_login', filterValue, onFilter),
    filter: getStringFilterFunc('last_login'),
    render(row: IUser) {
      return row.last_login ? isoToTurkishDateTime(row.last_login) : 'Never'
    }
  },
  userActionColumn((user) => popupComponent.value.openModal(user), confirmDelete)
]

function confirmDelete(user: IUser): void {
  window.$dialog.warning({
    title: 'Delete',
    content: `Delete ${user.username || 'this user'}?`,
    positiveText: 'Yes',
    negativeText: 'No',
    onPositiveClick: async () => {
      if (user.id !== undefined) await store.deleteUser(user.id)
    }
  })
}

function fetchUsers() {
  return store.fetchUsers({
    page: page.value,
    page_size: pageSize.value,
    username: filterValue.value.username,
    email: filterValue.value.email,
    first_name: filterValue.value.first_name,
    last_name: filterValue.value.last_name
  })
}

function handlePageUpdate(newPage: number) {
  page.value = newPage
  fetchUsers()
}

function handlePageSizeUpdate(newPageSize: number) {
  pageSize.value = newPageSize
  page.value = 1
  fetchUsers()
}

onMounted(() => {
  if (hasPermission.value) {
    fetchUsers()
    store.fetchPermissions({ page_size: 200 })
  }
  if (hasEffectivePermission('view_group') || userStore.getUser.is_superuser) {
    store.fetchGroups({ page_size: 200 })
  }
})

onUnmounted(() => {
  store.clearList()
})
</script>

<template>
  <div v-if="canAccessPage">
    <n-flex justify="space-between" align="center">
      <n-space>
        <InvitationLinkCreator :allowed="canInvite" :groups="store.getGroups" />
        <InvitationManager :allowed="canInvite" />
      </n-space>
      <n-text v-if="hasPermission"
        ><strong>Total: </strong>{{ store.usersPagination.count }}</n-text
      >
    </n-flex>
    <n-data-table
      v-if="hasPermission"
      :loading="store.isLoading"
      striped
      :columns="columns"
      :data="store.getUsers"
      remote
      :pagination="pagination"
      :row-key="(row: IUser) => row.id ?? row.username ?? row.email ?? 'unknown-user'"
      @update:page="handlePageUpdate"
      @update:page-size="handlePageSizeUpdate"
    />
    <UpdateForm v-if="hasPermission" ref="popupComponent" />
  </div>
  <div v-else>
    <Unauthorized />
  </div>
</template>
