<script setup lang="ts">
import { computed } from 'vue'
import { useThemeVars } from 'naive-ui'
import { useRouter } from 'vue-router'
import { useSessionStore } from '@/features/session/stores/session'

const router = useRouter()
const session = useSessionStore()

const themeVars = useThemeVars()

defineProps<{ collapsed?: boolean }>()
const displayName = computed(
  () =>
    [session.getUser.first_name, session.getUser.last_name].filter(Boolean).join(' ') ||
    session.getUser.username ||
    'Account'
)
const initials = computed(() =>
  displayName.value
    .split(/\s+/)
    .map((part) => part[0])
    .slice(0, 2)
    .join('')
    .toUpperCase()
)
</script>

<template>
  <n-button
    quaternary
    class="profile-trigger"
    :class="{ collapsed }"
    :aria-label="`Account and settings: ${displayName}`"
    title="Account and settings"
    @click="router.push({ name: 'settings' })"
  >
    <span class="profile-avatar" aria-hidden="true">{{ initials }}</span>
    <span v-if="!collapsed" class="profile-copy"
      ><strong>{{ displayName }}</strong
      ><span>Account &amp; settings</span></span
    >
  </n-button>
</template>

<style scoped>
.profile-trigger {
  flex-shrink: 0;
  width: 100%;
  height: auto;
  border-radius: 0;
  padding: 16px;
  border: 0;
  border-top: 1px solid v-bind('themeVars.borderColor');
  text-align: left;
  cursor: pointer;
}
.profile-trigger :deep(.n-button__content) {
  justify-content: flex-start;
  gap: 12px;
  width: 100%;
  min-width: 0;
}
.profile-trigger:focus-visible {
  outline: 2px solid v-bind('themeVars.primaryColor');
  outline-offset: -3px;
}
.profile-trigger.collapsed {
  padding: 16px 12px;
}
.profile-avatar {
  display: grid;
  place-items: center;
  flex-shrink: 0;
  width: 40px;
  height: 40px;
  border-radius: 50%;
  background: v-bind('themeVars.primaryColor');
  color: v-bind('themeVars.baseColor');
  font-weight: 600;
  font-size: 14px;
}
.profile-copy {
  display: grid;
  gap: 3px;
  min-width: 0;
}
.profile-copy strong {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-weight: 500;
  font-size: 13px;
}
.profile-copy > span {
  font-size: 11px;
  opacity: 0.65;
}
</style>
