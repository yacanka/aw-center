<template>
  <n-config-provider :theme="activeTheme" :theme-overrides="themeOverrides">
    <n-dialog-provider>
      <n-message-provider>
        <n-notification-provider>
          <n-loading-bar-provider>
            <UiFeedbackBridge>
              <RouterView v-if="isPublicPage" />
              <div v-else-if="isSessionInitializing" class="session-loading-shell">
                <n-spin size="small" />
                <span>Preparing AW Center...</span>
              </div>
              <AuthenticatedLayout v-else />
            </UiFeedbackBridge>
            <PwaInstallPrompt />
          </n-loading-bar-provider>
        </n-notification-provider>
      </n-message-provider>
    </n-dialog-provider>
  </n-config-provider>
</template>

<script setup lang="ts">
import { computed, defineAsyncComponent, watchEffect } from 'vue'
import { RouterView, useRoute } from 'vue-router'
import { darkTheme, lightTheme, type GlobalThemeOverrides } from 'naive-ui'
import UiFeedbackBridge from '@/app/components/UiFeedbackBridge.vue'
import PwaInstallPrompt from '@/app/components/PwaInstallPrompt.vue'
import { useSessionStore } from '@/features/session/stores/session'
import { applyPreferredTheme, resolvePreferredTheme } from './services/theme'

const AuthenticatedLayout = defineAsyncComponent(() => import('@/app/layouts/ProtectedLayout.vue'))
const userStore = useSessionStore()
const route = useRoute()
const activeThemeName = computed(() => resolvePreferredTheme(userStore.getPreferences))
const activeTheme = computed(() => (activeThemeName.value === 'dark' ? darkTheme : lightTheme))
const themeOverrides: GlobalThemeOverrides = {
  common: {
    fontFamily: "v-sans, system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif"
  }
}

watchEffect(() => {
  applyPreferredTheme(userStore.getPreferences)
})
const isSessionInitializing = computed(
  () => route.meta.public !== true && !userStore.isSessionInitialized
)
const isPublicPage = computed(() => route.meta.public === true)
</script>

<style>
.session-loading-shell {
  align-items: center;
  display: flex;
  gap: 0.75rem;
  min-height: 100dvh;
  justify-content: center;
}
</style>
