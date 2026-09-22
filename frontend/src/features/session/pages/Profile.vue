<script setup lang="ts">
import { computed, h } from 'vue'
import { Settings16Regular, Door16Regular } from '@vicons/fluent'
import { useRouter } from 'vue-router'
import { useSessionStore } from '@/features/session/stores/session'

const router = useRouter()
const session = useSessionStore()

const options = [
  {
    label: 'Settings',
    key: 'settings',
    icon: () => h(Settings16Regular, { style: 'width: 28px' })
  },
  { label: 'Logout', key: 'logout', icon: () => h(Door16Regular, { style: 'width: 28px' }) }
]

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

async function handleSelect(key: string | number) {
  if (key == 'settings') {
    router.push({ name: 'settings' })
  } else if (key == 'logout') {
    try {
      await session.logout()
      await router.push({ name: 'login' })
    } catch {
      // The server session may still be active; keep the authenticated UI in place.
    }
  }
}
</script>

<template>
  <n-dropdown trigger="click" :options="options" placement="top-start" @select="handleSelect">
    <button
      class="profile-trigger"
      :class="{ collapsed }"
      :aria-label="`Account menu: ${displayName}`"
    >
      <span class="profile-avatar" aria-hidden="true">{{ initials }}</span>
      <span v-if="!collapsed" class="profile-copy"
        ><strong>{{ displayName }}</strong
        ><span>Account &amp; settings</span></span
      >
    </button>
  </n-dropdown>
</template>

<style scoped>
.profile-trigger {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
  padding: 16px;
  border: 0;
  border-top: 1px solid rgba(128, 128, 128, 0.2);
  background: transparent;
  color: inherit;
  text-align: left;
  cursor: pointer;
}
.profile-trigger:hover {
  background: rgba(128, 128, 128, 0.1);
}
.profile-trigger:focus-visible {
  outline: 2px solid #002fa7;
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
  background: #002fa7;
  color: #fff;
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
