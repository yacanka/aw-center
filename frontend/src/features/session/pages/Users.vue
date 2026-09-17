<script setup lang="ts">
import { computed, h, ref, onMounted, onUnmounted } from 'vue'
import { NTag, NSpace, type DataTableColumns, type PaginationInfo } from 'naive-ui'
import { effectivePermissions } from '@/features/session/services/userAccess'
import { provideUserAdministrationController } from '@/features/session/composables/userAdministrationController'
import { IUser } from '@/features/session/models/auth'
import UpdateForm from '@/features/session/components/user/UserPopup.vue'
import Details from '@/features/session/components/user/DetailedInfo.vue'
import Unauthorized from '@/features/session/pages/Unauthorized.vue'
import { useSessionStore } from '@/features/session/stores/session'
import { isoToTurkishDateTime } from '@/shared/utils/time'
import { getStringFilterMenuFunc } from '@/shared/components/table/valueFilterMenus'
import { getStringFilterFunc } from '@/shared/services/tableFilters'
import InvitationLinkCreator from '@/features/session/components/user/InvitationLinkCreator.vue'
import InvitationManager from '@/features/session/components/user/InvitationManager.vue'
import { userActionColumn } from '@/features/session/services/userTableColumns'

const store = provideUserAdministrationController()
const userStore = useSessionStore()
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

const columns = computed<DataTableColumns<IUser>>(() => [
  {
    type: 'expand',
    expandable: () => true,
    renderExpand: (row) => {
      return h(Details, { user: row })
    },
    width: 48
  },
  {
    title: 'Username',
    key: 'username',
    width: 150,
    renderFilterMenu: getStringFilterMenuFunc('username', filterValue, onFilter),
    filter: getStringFilterFunc('username')
  },
  {
    title: 'Email',
    key: 'email',
    width: 260,
    renderFilterMenu: getStringFilterMenuFunc('email', filterValue, onFilter),
    filter: getStringFilterFunc('email'),
    ellipsis: {
      tooltip: true
    }
  },
  {
    title: 'First Name',
    key: 'first_name',
    width: 160,
    renderFilterMenu: getStringFilterMenuFunc('first_name', filterValue, onFilter),
    filter: getStringFilterFunc('first_name'),
    ellipsis: {
      tooltip: true
    }
  },
  {
    title: 'Last Name',
    key: 'last_name',
    width: 160,
    renderFilterMenu: getStringFilterMenuFunc('last_name', filterValue, onFilter),
    filter: getStringFilterFunc('last_name'),
    ellipsis: {
      tooltip: true
    }
  },
  {
    title: 'Roles',
    key: 'group_details',
    width: 220,
    render: (user) =>
      h(
        NSpace,
        { size: 'small' },
        {
          default: () => [
            ...(user.is_superuser
              ? [h(NTag, { type: 'warning', size: 'small' }, { default: () => 'Superuser' })]
              : []),
            ...(user.group_details || []).map((group) =>
              h(NTag, { size: 'small' }, { default: () => group.name })
            ),
            ...(!user.is_superuser && !user.group_details?.length ? ['No roles'] : [])
          ]
        }
      )
  },
  {
    title: 'Permissions',
    key: 'access',
    width: 190,
    render: (user) =>
      user.is_superuser
        ? 'All permissions'
        : `${effectivePermissions(user).length} assigned · ${user.permissions?.length || 0} direct`
  },
  {
    title: 'Account',
    key: 'is_active',
    width: 140,
    render: (user) => `${user.is_active ? 'Active' : 'Inactive'}${user.is_staff ? ' · Staff' : ''}`
  },
  {
    title: 'Last Login',
    key: 'last_login',
    width: 190,
    renderFilterMenu: getStringFilterMenuFunc('last_login', filterValue, onFilter),
    filter: getStringFilterFunc('last_login'),
    render(row: IUser) {
      return row.last_login ? isoToTurkishDateTime(row.last_login) : 'Never'
    }
  },
  userActionColumn((user) => popupComponent.value.openModal(user), confirmDelete, {
    update: hasEffectivePermission('change_user'),
    delete: hasEffectivePermission('delete_user')
  })
])

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
    void fetchUsers().catch(() => {})
    void store.fetchPermissions().catch(() => {})
  }
  if (hasEffectivePermission('view_group') || userStore.getUser.is_superuser) {
    void store.fetchGroups().catch(() => {})
  }
})

onUnmounted(() => {
  store.clearList()
})
</script>

<template>
  <div v-if="canAccessPage">
    <h2>Users &amp; access</h2>
    <p>
      Review roles and permissions for each user. Expand a row to see permission details and their
      sources.
    </p>
    <n-flex justify="space-between" align="center">
      <n-flex>
        <InvitationLinkCreator :allowed="canInvite" :groups="store.getGroups" />
        <InvitationManager :allowed="canInvite" />
      </n-flex>
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
      :scroll-x="1650"
      @update:page="handlePageUpdate"
      @update:page-size="handlePageSizeUpdate"
    />
    <UpdateForm v-if="hasPermission" ref="popupComponent" />
  </div>
  <div v-else>
    <Unauthorized />
  </div>
</template>
