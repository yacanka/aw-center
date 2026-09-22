<template>
  <n-modal
    v-model:show="showModal"
    preset="dialog"
    title="User roles and permissions"
    :mask-closable="!saving"
    :closable="!saving"
    :close-on-esc="!saving"
    class="app-modal app-modal--large user-editor"
    :show-icon="false"
  >
    <n-alert v-if="!canManageAccess" type="info" :bordered="false"
      >You can edit profile details. A superuser must change roles and account access.</n-alert
    >
    <n-form ref="formRef" :model="user" :rules="rules">
      <n-grid responsive="self" item-responsive :x-gap="12" :cols="12">
        <n-form-item-gi span="0:12 600:6" path="username" label="Username">
          <n-input v-model:value="user.username" disabled @keydown.enter.prevent />
        </n-form-item-gi>
        <n-form-item-gi span="0:12 600:6" path="email" label="Email">
          <n-input v-model:value="user.email" disabled @keydown.enter.prevent />
        </n-form-item-gi>
        <n-form-item-gi span="0:12 600:6" path="first_name" label="First Name">
          <n-input
            v-model:value="user.first_name"
            aria-label="First name"
            :disabled="saving"
            @keydown.enter.prevent
          />
        </n-form-item-gi>
        <n-form-item-gi span="0:12 600:6" path="last_name" label="Last Name">
          <n-input
            v-model:value="user.last_name"
            aria-label="Last name"
            :disabled="saving"
            @keydown.enter.prevent
          />
        </n-form-item-gi>
        <n-form-item-gi v-if="canManageAccess" span="12" label="Account access">
          <div class="account-controls">
            <n-checkbox
              v-model:checked="user.is_active"
              :disabled="saving || user.id === currentUserId || user.is_superuser"
              >Active account</n-checkbox
            >
            <n-checkbox
              v-model:checked="user.is_staff"
              :disabled="saving || user.id === currentUserId || user.is_superuser"
              >Administrator</n-checkbox
            >
            <p>
              Inactive accounts cannot sign in. Administrators still need the relevant permissions.
            </p>
          </div>
        </n-form-item-gi>
        <n-form-item-gi span="12" path="groups" label="Roles (groups)">
          <n-select
            v-model:value="user.groups"
            multiple
            filterable
            :disabled="!groupsReady || !canManageAccess || saving"
            clearable
            :options="groupOptions"
            placeholder="Select user groups"
          />
        </n-form-item-gi>
        <n-form-item-gi
          v-if="canManageAccess"
          span="12"
          path="permissions"
          label="Direct Permissions"
        >
          <div class="permission-editor">
            <n-input
              v-model:value="permissionSearch"
              placeholder="Search permissions or modules"
              clearable
            />
            <n-text depth="3"
              >{{ user.user_permissions?.length || 0 }} direct permissions selected. Role
              permissions remain active when a direct assignment is removed.</n-text
            >
            <div class="permission-options">
              <div v-for="section in permissionSections" :key="section.module">
                <h4>{{ section.module }}</h4>
                <div
                  v-for="permission in section.permissions"
                  :key="permission.id"
                  class="permission-option"
                >
                  <n-checkbox
                    :checked="user.user_permissions?.includes(Number(permission.id))"
                    :disabled="!permissionsReady || saving"
                    :aria-label="permission.name"
                    @update:checked="
                      (checked: boolean) => togglePermission(Number(permission.id), checked)
                    "
                  />
                  <PermissionLabel :permission="permission" />
                  <n-tag
                    v-if="inheritedIds.has(Number(permission.id))"
                    size="small"
                    :bordered="false"
                    >Via role</n-tag
                  >
                </div>
              </div>
              <n-empty v-if="!permissionSections.length" description="No matching permissions" />
            </div>
          </div>
        </n-form-item-gi>
      </n-grid>
    </n-form>

    <template #action>
      <n-button
        type="primary"
        :loading="saving"
        :disabled="canManageAccess && !permissionsReady"
        @click="updateDatabase"
        >Save changes</n-button
      >
      <n-button :disabled="saving" @click="closeModal">Cancel</n-button>
    </template>
  </n-modal>
</template>

<style scoped>
.user-editor :deep(.n-dialog__action) {
  position: sticky;
  bottom: -20px;
  background: var(--n-color);
  padding: 12px 0;
  z-index: 1;
}
.account-controls {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}
.account-controls p {
  width: 100%;
  margin: 0;
  color: var(--app-text-muted, #666);
  font-size: 12px;
}
.permission-editor {
  width: 100%;
  display: grid;
  gap: 12px;
}
.permission-options {
  max-height: 380px;
  overflow-y: auto;
}
.permission-option {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  padding: 6px 0;
}
h4 {
  margin: 16px 0 8px;
}
</style>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { NCheckbox, NAlert } from 'naive-ui'
import PermissionLabel from './PermissionLabel.vue'
import type { IPermission } from '@/features/session/models/auth'
import { IUser } from '@/features/session/models/auth'
import { useUserAdministrationController } from '@/features/session/composables/userAdministrationController'
import { FormRules, NModal } from 'naive-ui'
import { validateForm } from '@/shared/composables/forms'

const props = withDefaults(defineProps<{ canManageAccess?: boolean; currentUserId?: number }>(), {
  canManageAccess: false
})
const rules: FormRules = {}

const formRef = ref()
const showModal = ref(false)
const saving = ref(false)
const user = ref<IUser>({})
const permissionSearch = ref('')
const store = useUserAdministrationController()
const permissionsReady = computed(() => store.permissionsLoaded)
const groupsReady = computed(() => store.groupsLoaded)
const groupOptions = computed(() =>
  (groupsReady.value ? store.getGroups : user.value.group_details || []).map((group) => ({
    label: String(group.name),
    value: Number(group.id)
  }))
)
const inheritedIds = computed(
  () =>
    new Set(
      store.getGroups
        .filter((group) => user.value.groups?.includes(Number(group.id)))
        .flatMap((group) => (group.permissions || []).map((permission) => Number(permission.id)))
    )
)
const permissionSections = computed(() => {
  const sections = new Map<string, IPermission[]>()
  const search = permissionSearch.value.trim().toLowerCase()
  for (const permission of store.getPermissions) {
    const module = permission.content_type?.app_label || 'Other'
    if (!`${module} ${permission.name} ${permission.codename}`.toLowerCase().includes(search))
      continue
    if (!sections.has(module)) sections.set(module, [])
    sections.get(module)!.push(permission)
  }
  return [...sections].map(([module, permissions]) => ({ module, permissions }))
})

function togglePermission(id: number, checked: boolean) {
  const selected = new Set(user.value.user_permissions)
  if (checked) selected.add(id)
  else selected.delete(id)
  user.value.user_permissions = [...selected]
}

function openModal(value: IUser) {
  user.value = {
    ...value,
    groups: [...(value.groups || [])],
    user_permissions: [
      ...(value.user_permissions ||
        (value.permissions || []).map((permission) => Number(permission.id)))
    ]
  }
  permissionSearch.value = ''
  showModal.value = true
}

function closeModal() {
  showModal.value = false
}

async function updateDatabase() {
  if (!(await validateForm(formRef.value))) return
  if (user.value.id === undefined) throw new Error('Cannot update a user without an ID.')
  saving.value = true
  try {
    await store.updateUser(user.value.id, {
      first_name: user.value.first_name,
      last_name: user.value.last_name,
      ...(props.canManageAccess
        ? {
            ...(groupsReady.value ? { groups: user.value.groups } : {}),
            user_permissions: user.value.user_permissions,
            ...(user.value.id !== props.currentUserId && !user.value.is_superuser
              ? { is_active: user.value.is_active, is_staff: user.value.is_staff }
              : {})
          }
        : {})
    })
    closeModal()
  } catch {
    // The controller displays the API error; retain the draft for correction.
  } finally {
    saving.value = false
  }
}

defineExpose({ openModal })
</script>
