<script setup lang="ts">
import { computed } from 'vue'
import { useThemeVars } from 'naive-ui'
import type { IUser } from '@/features/session/models/auth'
import ProjectAccess from './ProjectAccess.vue'
import PermissionLabel from './PermissionLabel.vue'
import { effectivePermissions, permissionKey } from '@/features/session/services/userAccess'
const themeVars = useThemeVars()
const props = defineProps<{ user: IUser }>()
const permissions = computed(() => effectivePermissions(props.user))
function sources(key: string): string {
  const roles = (props.user.group_details || [])
    .filter((group) => group.permissions?.some((permission) => permissionKey(permission) === key))
    .map((group) => group.name)
  if (props.user.permissions?.some((permission) => permissionKey(permission) === key))
    roles.unshift('Direct')
  return roles.join(', ')
}
</script>

<template>
  <div class="access-details">
    <n-text v-if="!user.is_active" type="warning">Inactive account: access is disabled.</n-text>
    <n-text v-if="user.is_superuser"
      >Superuser: all permissions are granted while the account is active.</n-text
    >
    <n-text v-if="user.is_staff"
      >Staff: eligible to access Django administration with the required permissions.</n-text
    >
    <ProjectAccess :user="user" />
    <h3>System permissions · {{ permissions.length }}</h3>
    <p>
      Direct assignments and permissions inherited from roles. Project access rules still apply.
    </p>
    <div v-for="permission in permissions" :key="permissionKey(permission)" class="permission-row">
      <PermissionLabel :permission="permission" />
      <n-text depth="3">{{ sources(permissionKey(permission)) }}</n-text>
    </div>
    <n-empty v-if="!permissions.length" description="No role or direct permissions assigned" />
  </div>
</template>

<style scoped>
.access-details {
  padding: 12px 24px;
  display: grid;
  gap: 8px;
}
h3,
p {
  margin: 0;
}
p {
  margin-bottom: 8px;
}
.permission-row {
  display: flex;
  justify-content: space-between;
  gap: 24px;
  padding: 8px 0;
  border-bottom: 1px solid v-bind('themeVars.borderColor');
}
@media (max-width: 640px) {
  .permission-row {
    flex-direction: column;
    gap: 4px;
  }
}
</style>
