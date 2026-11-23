<script setup lang="ts">
import { useThemeVars } from 'naive-ui'
import { RouterLink, RouterView, useRoute, useRouter } from 'vue-router'
import Popup from '@/app/components/GlobalPopup.vue'
import { useSessionStore } from '@/features/session/stores/session'

const session = useSessionStore()
const route = useRoute()
const router = useRouter()
const themeVars = useThemeVars()
const themes = [
  { key: 'system', label: 'Sistem' },
  { key: 'light', label: 'Açık' },
  { key: 'dark', label: 'Koyu' }
]

async function changeTheme(theme: string | number): Promise<void> {
  if (theme !== 'system' && theme !== 'light' && theme !== 'dark') return
  try {
    await session.updatePreference({ theme })
  } catch {
    // The session store reports the failed update.
  }
}

async function logout(): Promise<void> {
  try {
    await session.logout()
    await router.replace({ name: 'login' })
  } catch {
    // Keep the current session when the server cannot sign it out.
  }
}
</script>

<template>
  <div class="certification-layout">
    <header class="certification-header">
      <RouterLink
        v-if="route.name !== 'compdocsHome' && route.name !== 'certificationProject'"
        :to="{ name: 'compdocsHome' }"
        custom
        v-slot="{ href, navigate }"
      >
        <n-button tag="a" quaternary :href="href" @click="navigate">Projeler</n-button>
      </RouterLink>
      <div class="certification-account">
        <n-dropdown trigger="click" :options="themes" @select="changeTheme">
          <n-button quaternary :disabled="session.loading">Tema</n-button>
        </n-dropdown>
        <n-button tertiary :disabled="session.loading" @click="logout">Çıkış yap</n-button>
      </div>
    </header>
    <main class="certification-content"><RouterView v-if="route.meta.certification" /></main>
  </div>
  <Popup />
</template>

<style scoped>
.certification-layout {
  min-height: 100dvh;
  background: v-bind('themeVars.bodyColor');
  color: v-bind('themeVars.textColorBase');
}

.certification-header {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  border-bottom: 1px solid v-bind('themeVars.borderColor');
  padding: 4px var(--app-gutter);
}

.certification-account {
  display: flex;
  gap: 8px;
  margin-inline-start: auto;
}

.certification-content {
  max-width: var(--app-content-max-width);
  min-width: 0;
  margin-inline: auto;
  padding: var(--app-gutter);
}

@media (max-width: 640px) {
  .certification-header :deep(.n-button) {
    min-height: 44px;
  }
}
</style>
