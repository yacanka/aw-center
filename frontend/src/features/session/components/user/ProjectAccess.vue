<script setup lang="ts">
import { NTag, NText, useThemeVars } from 'naive-ui'
import type { IUser } from '@/features/session/models/auth'

defineProps<{ user: IUser; compact?: boolean }>()
const themeVars = useThemeVars()
</script>

<template>
  <section
    class="project-access"
    :aria-label="compact ? 'Project access summary' : 'Project and application access'"
  >
    <template v-if="compact">
      <n-text v-if="user.is_active === false" type="warning">Account inactive</n-text>
      <n-text v-if="user.is_superuser">All projects and applications</n-text>
      <template v-else-if="user.project_access?.length">
        <n-tag
          v-for="access in user.project_access"
          :key="`${access.project_id}:${access.domain}`"
          size="small"
          :bordered="false"
        >
          {{ access.project_name }} · {{ access.application }} · {{ access.role
          }}{{ access.project_enabled ? '' : ' (project disabled)' }}
        </n-tag>
      </template>
      <n-text v-else depth="3">{{
        user.project_access ? 'No project roles assigned' : 'Project access unavailable'
      }}</n-text>
    </template>
    <template v-else>
      <h3>Project &amp; application access</h3>
      <p>
        Roles are scoped to one project and application. The strongest direct or group role applies.
        Application availability and record rules still apply.
      </p>
      <n-text v-if="user.is_superuser"
        >Superuser: highest role in every project application while the account is active. Disabled
        projects remain unavailable.</n-text
      >
      <div
        v-for="access in user.project_access"
        :key="`${access.project_id}:${access.domain}`"
        class="project-entry"
      >
        <div class="project-heading">
          <strong>{{ access.project_name }} · {{ access.application }}</strong>
          <n-tag size="small" :bordered="false">{{ access.role }}</n-tag>
          <n-tag v-if="!access.project_enabled" size="small" type="warning">Project disabled</n-tag>
        </div>
        <n-text depth="3">{{ access.project_slug }}</n-text>
        <div v-for="(source, index) in access.sources" :key="index">
          {{ source.kind === 'direct' ? 'Direct assignment' : `Via role: ${source.group_name}` }} ·
          {{ source.role }}
        </div>
      </div>
      <n-text v-if="!user.is_superuser && !user.project_access?.length" depth="3">{{
        user.project_access
          ? 'No project roles assigned directly or through groups.'
          : 'Project access unavailable. Refresh the user directory.'
      }}</n-text>
    </template>
  </section>
</template>

<style scoped>
.project-access {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  min-width: 0;
  overflow-wrap: anywhere;
}
h3,
p {
  width: 100%;
  margin: 0;
}
p {
  color: v-bind('themeVars.textColor3');
}
.project-entry {
  width: 100%;
  padding: 12px 0;
  border-bottom: 1px solid v-bind('themeVars.borderColor');
}
.project-heading {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}
.project-access :deep(.n-tag) {
  height: auto;
  min-height: var(--n-height);
  white-space: normal;
}
</style>
