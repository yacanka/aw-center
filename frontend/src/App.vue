<template>
  <n-config-provider :theme="activeTheme">
    <n-dialog-provider>
      <n-message-provider>
        <n-notification-provider>
          <n-loading-bar-provider>
            <div v-if="isSessionInitializing" class="session-loading-shell">
              <n-spin size="small" />
              <span>Preparing AW Center...</span>
            </div>
            <MainView v-else />
          </n-loading-bar-provider>
        </n-notification-provider>
      </n-message-provider>
    </n-dialog-provider>
  </n-config-provider>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { darkTheme, lightTheme } from 'naive-ui'
import MainView from '@/views/MainView.vue'
import { useUserStore } from './stores/user'

const userStore = useUserStore()
const activeTheme = computed(() =>
  userStore.getPreferences.theme === 'dark' ? darkTheme : lightTheme
)
const isSessionInitializing = computed(() => !userStore.isSessionInitialized)
</script>

<style>
body,
html {
  margin: 0;
  padding: 0;
  transition: background-color 100s ease;
}

.session-loading-shell {
  align-items: center;
  display: flex;
  gap: 0.75rem;
  height: 100vh;
  justify-content: center;
}
</style>
