<script setup lang="ts">
import { h, ref } from 'vue'
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

const showNotification = ref(true)

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

const notificationValue = ref(1)
</script>

<template>
  <n-dropdown trigger="hover" :options="options" @select="handleSelect">
    <n-badge processing :show="showNotification" :value="notificationValue" :offset="[-4, 5]">
      <n-avatar round size="large"> {{ session.getUser.username }} </n-avatar>
    </n-badge>
  </n-dropdown>
</template>
