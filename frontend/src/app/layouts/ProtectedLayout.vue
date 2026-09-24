<template>
  <ParticleBackground v-if="useSessionStore().getPreferences.has_particles" />
  <n-layout has-sider class="transparent protected-shell">
    <n-layout-sider
      bordered
      collapse-mode="width"
      :collapsed="collapsed"
      :collapsed-width="64"
      :width="240"
      :show-trigger="!isNarrow"
      class="transparent protected-sider"
      @update:collapsed="handleCollapsedUpdate"
    >
      <div class="sider-navigation">
        <n-menu
          :options="menuOptions"
          :value="currentPage"
          :collapsed-width="64"
          :collapsed-icon-size="22"
          @update:value="handleMenuSelect"
        />
      </div>
      <Profile :collapsed="collapsed" />
    </n-layout-sider>

    <div class="protected-main">
      <n-layout-content class="transparent protected-content" content-class="protected-scroll">
        <main class="protected-page">
          <RouterView />
        </main>
      </n-layout-content>
      <footer class="protected-footer">AW Center · v{{ appVersion }} · © 2026</footer>
    </div>
    <CommandPalette :options="menuOptions" />
    <ReleaseNotesModal />
  </n-layout>
  <Popup />
</template>

<script setup lang="ts">
import { ref, computed, provide, watch } from 'vue'
import { useThemeVars } from 'naive-ui'
import { RouterView, useRouter, useRoute } from 'vue-router'
import ParticleBackground from '@/shared/components/ParticleBackground.vue'
import Profile from '@/features/session/pages/Profile.vue'
import Popup from '@/app/components/GlobalPopup.vue'
import { useSessionStore } from '@/features/session/stores/session'
import ReleaseNotesModal from '@/app/components/ReleaseNotesModal.vue'
import { useReleaseNotesStore } from '@/app/stores/releaseNotes'
import { formatApiError } from '@/shared/api/apiError'
import { createMainMenuOptions, MAIN_MENU_OPTIONS_KEY } from '@/app/services/mainMenu'
import CommandPalette from '@/app/components/navigation/CommandPalette.vue'
import { useProjectCatalogStore } from '@/features/projects/stores/projectCatalog'
import { useMediaQuery } from '@/shared/composables/mediaQuery'

const themeVars = useThemeVars()
const userStore = useSessionStore()
const projectCatalog = useProjectCatalogStore()

const router = useRouter()
const route = useRoute()
const releaseNotes = useReleaseNotesStore()

function handleMenuSelect(key: string) {
  router.push(key)
}

const menuOptions = computed(() =>
  createMainMenuOptions(
    projectCatalog.complianceProjects,
    userStore.getUser,
    projectCatalog.hasAnyRole('dcc'),
    projectCatalog.hasAnyRole('organization')
  )
)
provide(MAIN_MENU_OPTIONS_KEY, menuOptions)

const currentPage = computed(() => route.path)
const appVersion = import.meta.env.VITE_VERSION
const isNarrow = useMediaQuery('(max-width: 900px)')
const desktopCollapsed = ref(false)
const collapsed = computed(() => isNarrow.value || desktopCollapsed.value)

function handleCollapsedUpdate(value: boolean): void {
  if (!isNarrow.value) desktopCollapsed.value = value
}

const authenticatedShellLoaded = ref(false)

async function initializeAuthenticatedShell() {
  if (authenticatedShellLoaded.value || !userStore.getUser.id) return
  authenticatedShellLoaded.value = true
  await loadProjectRegistry()
  await releaseNotes.checkUnseen()
}

watch(
  () => userStore.getUser.id,
  (userId, previousUserId) => {
    if (!userId || (previousUserId && previousUserId !== userId)) {
      authenticatedShellLoaded.value = false
    }
    if (userId) void initializeAuthenticatedShell()
  },
  { immediate: true }
)

async function loadProjectRegistry() {
  try {
    await projectCatalog.load()
  } catch (error) {
    window.$message.warning(`Project list could not be refreshed: ${formatApiError(error)}`)
  }
}
</script>

<style scoped>
.transparent {
  background-color: transparent !important;
}

/* Bound the shell so only the navigation and page scroll containers can scroll. */
.protected-shell {
  height: 100dvh;
  min-width: 0;
  overflow: hidden;
}

.protected-shell :deep(> .n-layout-scroll-container) {
  overflow: hidden;
}

.protected-main {
  display: flex;
  flex: 1;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  min-width: 0;
  overflow: hidden;
}

.protected-sider {
  height: 100%;
}

.protected-sider :deep(.n-layout-sider-scroll-container) {
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.sider-navigation {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  overscroll-behavior: contain;
}

.protected-content {
  flex: 1;
  min-height: 0;
  min-width: 0;
}

.protected-content :deep(.protected-scroll) {
  padding: var(--app-gutter);
  overscroll-behavior: contain;
}

.protected-page {
  margin-inline: auto;
  max-width: var(--app-content-max-width);
  min-width: 0;
  width: 100%;
}

.protected-footer {
  flex-shrink: 0;
  background: v-bind('themeVars.bodyColor');
  border-top: 1px solid v-bind('themeVars.borderColor');
  color: v-bind('themeVars.textColor3');
  font-size: 11px;
  padding: 6px var(--app-gutter) max(6px, env(safe-area-inset-bottom));
  text-align: right;
}
</style>
