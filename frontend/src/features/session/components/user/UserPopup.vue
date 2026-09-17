<template>
  <n-modal
    v-model:show="showModal"
    preset="dialog"
    title="User roles and permissions"
    centered
    class="app-modal app-modal--large"
  >
    <n-form ref="formRef" :model="user" :rules="rules">
      <n-grid responsive="self" item-responsive :x-gap="12" :cols="12">
        <n-form-item-gi span="0:12 720:3" path="username" label="Username">
          <n-input v-model:value="user.username" disabled @keydown.enter.prevent />
        </n-form-item-gi>
        <n-form-item-gi span="0:12 720:5" path="email" label="Email">
          <n-input v-model:value="user.email" disabled @keydown.enter.prevent />
        </n-form-item-gi>
        <n-form-item-gi span="0:12 720:2" path="first_name" label="First Name">
          <n-input v-model:value="user.first_name" @keydown.enter.prevent />
        </n-form-item-gi>
        <n-form-item-gi span="0:12 720:2" path="last_name" label="Last Name">
          <n-input v-model:value="user.last_name" @keydown.enter.prevent />
        </n-form-item-gi>
        <n-form-item-gi span="12" path="groups" label="Roles (groups)">
          <n-select
            v-model:value="user.groups"
            multiple
            filterable
            :disabled="!groupsReady"
            clearable
            :options="groupOptions"
            placeholder="Select user groups"
          />
        </n-form-item-gi>
        <n-form-item-gi span="12" path="permissions" label="Direct Permissions">
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
                    :disabled="!permissionsReady"
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
        :disabled="!permissionsReady"
        @click="updateDatabase"
        >Save changes</n-button
      >
    </template>
  </n-modal>
</template>

<style scoped>
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
  gap: 8px;
  padding: 6px 0;
}
h4 {
  margin: 16px 0 8px;
}
</style>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { NCheckbox } from 'naive-ui'
import PermissionLabel from './PermissionLabel.vue'
import type { IPermission } from '@/features/session/models/auth'
import { IUser } from '@/features/session/models/auth'
import { useUserAdministrationController } from '@/features/session/composables/userAdministrationController'
import { FormRules, NModal } from 'naive-ui'
import { validateForm } from '@/shared/composables/forms'

const rules = ref<FormRules>({
  username: [
    {
      required: true,
      trigger: 'blur'
    }
  ],
  email: [
    {
      required: true,
      trigger: 'blur'
    }
  ],
  first_name: [
    {
      required: true,
      trigger: 'blur'
    }
  ],
  last_name: [
    {
      required: true,
      trigger: 'blur'
    }
  ]
})

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
      ...(groupsReady.value ? { groups: user.value.groups } : {}),
      user_permissions: user.value.user_permissions
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
