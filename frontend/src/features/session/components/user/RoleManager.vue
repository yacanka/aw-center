<script setup lang="ts">
import { computed, ref } from 'vue'
import { NButton, NModal, NInput, NCheckbox, NAlert, NEmpty } from 'naive-ui'
import { useUserAdministrationController } from '@/features/session/composables/userAdministrationController'
import type { IGroup } from '@/features/session/models/auth'
import RoleBadge from './RoleBadge.vue'
import PermissionLabel from './PermissionLabel.vue'
const emit = defineEmits<{ changed: [] }>()
const store = useUserAdministrationController()
const show = ref(false)
const saving = ref(false)
const id = ref<number>()
const name = ref('')
const selected = ref<number[]>([])
const search = ref('')
const ready = computed(() => store.groupsLoaded && store.permissionsLoaded)
const permissions = computed(() =>
  store.getPermissions.filter((permission) =>
    `${permission.name} ${permission.content_type?.app_label} ${permission.codename}`
      .toLowerCase()
      .includes(search.value.toLowerCase())
  )
)
function edit(group?: IGroup) {
  id.value = group?.id
  name.value = group?.name || ''
  selected.value = (group?.permissions || []).map((permission) => Number(permission.id))
  search.value = ''
  show.value = true
}
function toggle(value: number, checked: boolean) {
  selected.value = checked
    ? [...new Set([...selected.value, value])]
    : selected.value.filter((id) => id !== value)
}
async function save() {
  if (!name.value.trim() || !ready.value || saving.value) return
  saving.value = true
  try {
    await store.saveGroup(id.value, name.value.trim(), selected.value)
    show.value = false
    emit('changed')
  } catch {
    /* The controller reports errors and the draft stays open. */
  } finally {
    saving.value = false
  }
}
function remove(group: IGroup) {
  window.$dialog.warning({
    title: `Delete ${group.name}?`,
    content:
      'Every member will lose permissions inherited from this role. Direct assignments and other roles remain.',
    positiveText: 'Delete role',
    negativeText: 'Cancel',
    onPositiveClick: async () => {
      try {
        await store.deleteGroup(Number(group.id))
        emit('changed')
      } catch {
        return false
      }
    }
  })
}
async function reload() {
  await Promise.allSettled([store.fetchGroups(), store.fetchPermissions()])
}
</script>
<template>
  <section class="role-manager">
    <header>
      <div>
        <h2>Shared roles</h2>
        <p>Define access once. Apply it consistently to your team.</p>
      </div>
      <n-button :disabled="!ready" @click="edit()">Create role</n-button>
    </header>
    <n-alert v-if="!ready" type="warning"
      >Role catalogs are unavailable or still loading.
      <n-button text @click="reload">Retry</n-button></n-alert
    >
    <div class="role-grid">
      <article v-for="group in store.getGroups" :key="group.id">
        <RoleBadge :group="group" />
        <p>{{ group.permissions?.length || 0 }} permissions</p>
        <div class="role-actions">
          <n-button size="small" :disabled="!ready" @click="edit(group)">Edit role</n-button
          ><n-button size="small" quaternary type="error" :disabled="!ready" @click="remove(group)"
            >Delete</n-button
          >
        </div>
      </article>
    </div>
    <n-empty v-if="ready && !store.getGroups.length" description="No shared roles yet" />
    <n-modal
      v-model:show="show"
      preset="dialog"
      :title="id ? 'Edit shared role' : 'Create shared role'"
      class="app-modal app-modal--large"
      :mask-closable="!saving"
      :closable="!saving"
      :close-on-esc="!saving"
    >
      <div class="role-form">
        <n-alert v-if="id" type="warning" :bordered="false"
          >Saving changes updates access for every member of this role.</n-alert
        >
        <label
          >Role name<n-input
            v-model:value="name"
            :maxlength="150"
            :disabled="saving"
            placeholder="Enter a role name"
        /></label>
        <label
          >Find permissions<n-input
            v-model:value="search"
            clearable
            placeholder="Search permissions or modules"
        /></label>
        <span>{{ selected.length }} permissions selected</span>
        <div class="role-permissions">
          <label v-for="permission in permissions" :key="permission.id"
            ><n-checkbox
              :checked="selected.includes(Number(permission.id))"
              :disabled="saving"
              :aria-label="permission.name"
              @update:checked="
                (checked: boolean) => toggle(Number(permission.id), checked)
              " /><PermissionLabel :permission="permission" /></label
          ><n-empty v-if="!permissions.length" description="No matching permissions" />
        </div>
      </div>
      <template #action
        ><n-button :disabled="saving" @click="show = false">Cancel</n-button
        ><n-button
          type="primary"
          :loading="saving"
          :disabled="!name.trim() || !ready"
          @click="save"
          >{{ id ? 'Save role for all members' : 'Create role' }}</n-button
        ></template
      >
    </n-modal>
  </section>
</template>
<style scoped>
.role-manager {
  margin-top: 28px;
}
header {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: center;
  flex-wrap: wrap;
  margin-bottom: 20px;
}
h2 {
  margin: 0;
  font-size: 19px;
}
p {
  color: #646975;
  margin: 8px 0 16px;
  font-size: 13px;
}
header p {
  margin-bottom: 0;
}
.role-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 240px), 1fr));
  gap: 12px;
}
article {
  border: 1px solid #e4e5e9;
  padding: 20px;
  min-width: 0;
}
.role-actions {
  display: flex;
  gap: 8px;
}
.role-form {
  display: grid;
  gap: 16px;
  padding-top: 12px;
}
.role-form > label {
  display: grid;
  gap: 6px;
}
.role-permissions {
  max-height: min(42vh, 400px);
  overflow: auto;
}
.role-permissions > label {
  display: flex;
  gap: 10px;
  padding: 10px 0;
  align-items: center;
  border-bottom: 1px solid #8882;
}
</style>
