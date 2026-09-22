<script setup lang="ts">
import { computed, h, ref, onMounted, onUnmounted, watch } from 'vue'
import {
  NConfigProvider,
  NButton,
  NTag,
  NInput,
  NSelect,
  NPagination,
  NAlert,
  NEmpty,
  NDataTable,
  NSpin,
  type DataTableColumns
} from 'naive-ui'
import { provideUserAdministrationController } from '@/features/session/composables/userAdministrationController'
import type { IUser } from '@/features/session/models/auth'
import UpdateForm from '@/features/session/components/user/UserPopup.vue'
import Details from '@/features/session/components/user/DetailedInfo.vue'
import RoleBadge from '@/features/session/components/user/RoleBadge.vue'
import RoleManager from '@/features/session/components/user/RoleManager.vue'
import Unauthorized from '@/features/session/pages/Unauthorized.vue'
import { useSessionStore } from '@/features/session/stores/session'
import { isoToTurkishDateTime } from '@/shared/utils/time'
import InvitationLinkCreator from '@/features/session/components/user/InvitationLinkCreator.vue'
import InvitationManager from '@/features/session/components/user/InvitationManager.vue'

const store = provideUserAdministrationController()
const session = useSessionStore()
const page = ref(1)
const pageSize = ref(12)
const search = ref('')
const account = ref('all')
const error = ref(false)
const popup = ref<InstanceType<typeof UpdateForm>>()
const expanded = ref<number | null>(null)
const isAdmin = computed(() => Boolean(session.getUser.is_staff || session.getUser.is_superuser))
const canView = computed(() => isAdmin.value && session.hasEffectiveRole('auth', 'view_user'))
const canInvite = computed(() => isAdmin.value && session.hasEffectiveRole('auth', 'add_user'))
const canAccess = computed(() => canView.value || canInvite.value)
const canManageRoles = computed(() => Boolean(session.getUser.is_superuser))
const accountOptions = [
  { label: 'All accounts', value: 'all' },
  { label: 'Active', value: 'active' },
  { label: 'Inactive', value: 'inactive' },
  { label: 'Administrators', value: 'admin' }
]
function canEdit(user: IUser) {
  return (
    session.hasEffectiveRole('auth', 'change_user') &&
    (canManageRoles.value || (!user.is_staff && !user.is_superuser))
  )
}
function canDelete(user: IUser) {
  return (
    session.hasEffectiveRole('auth', 'delete_user') &&
    user.id !== session.getUser.id &&
    !user.is_superuser &&
    (canManageRoles.value || !user.is_staff)
  )
}
function name(user: IUser) {
  return [user.first_name, user.last_name].filter(Boolean).join(' ') || user.username || 'User'
}
function roles(user: IUser) {
  return [
    ...(user.is_superuser
      ? [
          h(RoleBadge, {
            name: 'Superuser',
            description:
              'Full system access. Can manage administrators, roles and all permissions.',
            critical: true
          })
        ]
      : user.is_staff
        ? [
            h(RoleBadge, {
              name: 'Administrator',
              description: 'Can use administration tools only with the required permissions.',
              critical: true
            })
          ]
        : []),
    ...(user.group_details || []).map((group) => h(RoleBadge, { group })),
    ...(!user.is_superuser && !user.is_staff && !user.group_details?.length
      ? [h('span', { class: 'muted' }, 'No roles assigned')]
      : [])
  ]
}
const columns = computed<DataTableColumns<IUser>>(() => [
  { type: 'expand', renderExpand: (user) => h(Details, { user }), width: 42 },
  {
    title: 'User',
    key: 'username',
    minWidth: 210,
    render: (user) =>
      h('div', { class: 'user-identity' }, [
        h('strong', name(user)),
        h('span', user.email || user.username)
      ])
  },
  {
    title: 'Roles & access',
    key: 'roles',
    minWidth: 230,
    render: (user) => h('div', { class: 'role-list' }, roles(user))
  },
  {
    title: 'Status',
    key: 'is_active',
    width: 100,
    render: (user) =>
      h(
        NTag,
        { size: 'small', bordered: false, type: user.is_active ? 'success' : 'default' },
        { default: () => (user.is_active ? 'Active' : 'Inactive') }
      )
  },
  {
    title: 'Last sign in',
    key: 'last_login',
    width: 165,
    render: (user) => (user.last_login ? isoToTurkishDateTime(user.last_login) : 'Never signed in')
  },
  {
    title: 'Actions',
    key: 'actions',
    width: 170,
    render: (user) =>
      h('div', { class: 'row-actions' }, [
        ...(canEdit(user)
          ? [
              h(
                NButton,
                { size: 'small', onClick: () => popup.value?.openModal(user) },
                { default: () => 'Manage' }
              )
            ]
          : []),
        ...(canDelete(user)
          ? [
              h(
                NButton,
                {
                  size: 'small',
                  quaternary: true,
                  type: 'error',
                  onClick: () => confirmDelete(user)
                },
                { default: () => 'Delete' }
              )
            ]
          : [])
      ])
  }
])
function confirmDelete(user: IUser) {
  window.$dialog.warning({
    title: `Delete ${user.username}?`,
    content:
      'This permanently deletes the account and its access. Consider deactivating the account instead.',
    positiveText: 'Delete account',
    negativeText: 'Cancel',
    onPositiveClick: async () => {
      try {
        if (user.id !== undefined) await store.deleteUser(user.id)
        if (store.getUsers.length === 0 && page.value > 1) page.value--
        await fetchUsers()
      } catch {
        return false
      }
    }
  })
}
async function fetchUsers() {
  if (!canView.value) return
  error.value = false
  try {
    await store.fetchUsers({
      page: page.value,
      page_size: pageSize.value,
      search: search.value.trim(),
      account: account.value
    })
  } catch {
    error.value = true
  }
}
function applyFilters() {
  page.value = 1
  void fetchUsers()
}
function paginate(value: number) {
  page.value = value
  void fetchUsers()
}
let searchTimer: ReturnType<typeof setTimeout> | undefined
watch(search, () => {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(applyFilters, 300)
})
watch(account, applyFilters)
async function loadCatalogs() {
  if (!canAccess.value) return
  await Promise.allSettled([
    ...(canView.value ? [store.fetchPermissions()] : []),
    ...(session.hasEffectiveRole('auth', 'view_group') ? [store.fetchGroups()] : [])
  ])
}
onMounted(() => {
  void fetchUsers()
  void loadCatalogs()
})
onUnmounted(() => {
  clearTimeout(searchTimer)
  store.clearList()
})
</script>

<template>
  <n-config-provider
    v-if="canAccess"
    :theme="null"
    :theme-overrides="{
      common: {
        primaryColor: '#002FA7',
        primaryColorHover: '#1749B8',
        primaryColorPressed: '#00288D'
      }
    }"
  >
    <section class="users-admin">
      <header class="page-heading">
        <div>
          <div class="section-label">Administration</div>
          <h1>Users &amp; access<span class="heading-dot">.</span></h1>
          <p>Manage your people, account access and shared roles.</p>
        </div>
        <div class="invite-actions">
          <InvitationManager :allowed="canInvite" /><InvitationLinkCreator
            :allowed="canInvite"
            :groups="canManageRoles ? store.getGroups : []"
          />
        </div>
      </header>
      <div class="access-overview">
        <div class="overview-count">
          <strong>{{ canView ? store.usersPagination.count : '—' }}</strong
          ><span>{{ search || account !== 'all' ? 'Matching accounts' : 'User accounts' }}</span>
        </div>
        <div>
          <strong>Role-based access</strong>
          <p>Roles combine permissions. Direct permissions add access for one person.</p>
        </div>
        <div>
          <strong>Protected administration</strong>
          <p>Only superusers can change roles, permissions and administrator status.</p>
        </div>
      </div>
      <template v-if="canView">
        <div class="directory-heading">
          <h2>User directory</h2>
          <n-button :loading="store.isLoading" @click="fetchUsers">Refresh</n-button>
        </div>
        <form class="directory-filters" @submit.prevent="applyFilters">
          <label
            >Search users<n-input
              v-model:value="search"
              clearable
              placeholder="Search name, username or email"
          /></label>
          <label
            >Account status<n-select v-model:value="account" :options="accountOptions"
          /></label>
        </form>
        <n-alert v-if="error" type="error" class="directory-error" title="Users could not be loaded"
          >Try refreshing the directory. Previously loaded results may be out of date.</n-alert
        >
        <div class="desktop-directory">
          <n-data-table
            :loading="store.isLoading"
            :columns="columns"
            :data="store.getUsers"
            :row-key="(user: IUser) => user.id!"
            :scroll-x="920"
            :bordered="false"
          />
        </div>
        <n-spin :show="store.isLoading" class="mobile-directory">
          <div class="user-cards">
            <article v-for="user in store.getUsers" :key="user.id" class="user-card">
              <header>
                <div class="user-identity">
                  <strong>{{ name(user) }}</strong
                  ><span>{{ user.username }}</span>
                </div>
                <n-tag
                  size="small"
                  :bordered="false"
                  :type="user.is_active ? 'success' : 'default'"
                  >{{ user.is_active ? 'Active' : 'Inactive' }}</n-tag
                >
              </header>
              <p class="user-email">{{ user.email || 'No email address' }}</p>
              <div class="role-list">
                <RoleBadge
                  v-if="user.is_superuser"
                  name="Superuser"
                  description="Full system access. Can manage administrators, roles and all permissions."
                  critical
                /><RoleBadge
                  v-else-if="user.is_staff"
                  name="Administrator"
                  description="Administration access requires the relevant permissions."
                  critical
                /><RoleBadge
                  v-for="group in user.group_details"
                  :key="group.id"
                  :group="group"
                /><span
                  v-if="!user.is_staff && !user.is_superuser && !user.group_details?.length"
                  class="muted"
                  >No roles assigned</span
                >
              </div>
              <footer>
                <n-button
                  size="small"
                  quaternary
                  @click="expanded = expanded === user.id ? null : user.id!"
                  >{{ expanded === user.id ? 'Hide access' : 'View access' }}</n-button
                >
                <div class="row-actions">
                  <n-button v-if="canEdit(user)" size="small" @click="popup?.openModal(user)"
                    >Manage</n-button
                  ><n-button
                    v-if="canDelete(user)"
                    size="small"
                    quaternary
                    type="error"
                    @click="confirmDelete(user)"
                    >Delete</n-button
                  >
                </div>
              </footer>
              <Details v-if="expanded === user.id" :user="user" />
            </article>
            <n-empty
              v-if="!store.getUsers.length && !store.isLoading"
              description="No users match these filters"
            />
          </div>
        </n-spin>
        <div class="directory-pagination">
          <span>{{ store.usersPagination.count }} results</span
          ><n-pagination
            :page="page"
            :page-size="pageSize"
            :item-count="store.usersPagination.count"
            :page-slot="3"
            @update:page="paginate"
          />
        </div>
        <UpdateForm
          ref="popup"
          :can-manage-access="canManageRoles"
          :current-user-id="session.getUser.id"
        />
      </template>
      <RoleManager v-if="canManageRoles" @changed="fetchUsers" />
    </section>
  </n-config-provider>
  <Unauthorized v-else />
</template>

<style scoped>
.users-admin {
  --admin-accent: #002fa7;
  color: #20232b;
  background: #fff;
  font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
  padding: clamp(18px, 3vw, 40px);
  border: 1px solid #e4e5e9;
  min-width: 0;
}
.page-heading {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 24px;
  flex-wrap: wrap;
  padding-bottom: 28px;
}
.section-label {
  color: var(--admin-accent);
  font-size: 12px;
  font-weight: 700;
  margin-bottom: 10px;
}
h1 {
  font-size: clamp(28px, 3vw, 42px);
  line-height: 1.1;
  letter-spacing: -1.5px;
  margin: 0;
  font-weight: 600;
}
.heading-dot {
  color: var(--admin-accent);
}
p {
  color: #646975;
  margin: 12px 0 0;
  line-height: 1.6;
}
.invite-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.access-overview {
  display: grid;
  grid-template-columns: 180px 1fr 1fr;
  border-block: 1px solid #e4e5e9;
  background: #f7f7f8;
}
.access-overview > div {
  padding: 22px;
  border-right: 1px solid #e4e5e9;
}
.access-overview > div:last-child {
  border: 0;
}
.access-overview p {
  font-size: 13px;
  margin-top: 6px;
}
.overview-count {
  display: flex;
  gap: 12px;
  align-items: center;
}
.overview-count strong {
  font-size: 36px;
  font-weight: 500;
  letter-spacing: -1px;
  color: var(--admin-accent);
  font-variant-numeric: tabular-nums;
}
.overview-count span {
  font-size: 12px;
  color: #646975;
}
.directory-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin: 28px 0 16px;
}
h2 {
  font-size: 19px;
  margin: 0;
}
.directory-filters {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 220px;
  gap: 16px;
  margin-bottom: 20px;
}
.directory-filters label {
  display: grid;
  gap: 7px;
  font-size: 12px;
  font-weight: 600;
  min-width: 0;
}
.directory-error {
  margin-bottom: 16px;
}
:deep(.user-identity) {
  display: grid;
  gap: 4px;
  min-width: 0;
  overflow-wrap: anywhere;
}
:deep(.user-identity span),
.muted {
  color: #646975;
  font-size: 12px;
}
:deep(.role-list) {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
}
:deep(.row-actions) {
  display: flex;
  gap: 6px;
}
.directory-pagination {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  padding: 20px 0;
  border-bottom: 1px solid #e4e5e9;
}
.directory-pagination > span {
  color: #646975;
  font-size: 12px;
}
.mobile-directory {
  display: none;
}
@media (max-width: 1000px) {
  .access-overview {
    grid-template-columns: 140px 1fr;
  }
  .access-overview > div:last-child {
    grid-column: 1/-1;
    border-top: 1px solid #e4e5e9;
  }
}
@media (max-width: 700px) {
  .users-admin {
    padding: 18px 14px;
  }
  .page-heading {
    gap: 20px;
  }
  .invite-actions {
    width: 100%;
  }
  .access-overview {
    grid-template-columns: 1fr;
  }
  .access-overview > div {
    padding: 16px;
    border-right: 0;
    border-bottom: 1px solid #e4e5e9;
  }
  .access-overview > div:last-child {
    border-top: 0;
  }
  .directory-filters {
    grid-template-columns: 1fr;
    gap: 12px;
  }
  .desktop-directory {
    display: none;
  }
  .mobile-directory {
    display: block;
  }
  .user-cards {
    display: grid;
    gap: 12px;
  }
  .user-card {
    padding: 16px;
    border: 1px solid #e4e5e9;
    min-width: 0;
  }
  .user-card header,
  .user-card footer {
    display: flex;
    justify-content: space-between;
    gap: 8px;
    align-items: center;
    flex-wrap: wrap;
  }
  .user-card footer {
    margin-top: 18px;
    padding-top: 12px;
    border-top: 1px solid #e4e5e9;
  }
  .user-email {
    overflow-wrap: anywhere;
    margin: 10px 0 14px;
    font-size: 13px;
  }
  .directory-pagination {
    flex-wrap: wrap;
  }
  :deep(.access-details) {
    padding: 16px 0 0;
  }
}
</style>
