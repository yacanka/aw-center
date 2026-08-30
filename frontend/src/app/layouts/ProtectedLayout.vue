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
      <n-menu
        :options="menuOptions"
        :value="currentPage"
        :collapsed-width="64"
        :collapsed-icon-size="22"
        @update:value="handleMenuSelect"
      />
    </n-layout-sider>

    <n-layout class="transparent protected-main">
      <n-layout-content class="transparent protected-content">
        <main class="protected-page">
          <RouterView />
        </main>
        <footer class="protected-footer">AW Center (v{{ appVersion }}) © 2026</footer>
      </n-layout-content>
    </n-layout>
    <CommandPalette :options="menuOptions" />
    <ReleaseNotesModal />
  </n-layout>
  <Popup />
</template>

<script setup lang="ts">
import { ref, computed, provide, watch } from 'vue'
import { RouterView, useRouter, useRoute } from 'vue-router'
import ParticleBackground from '@/shared/components/ParticleBackground.vue'
import Popup from '@/app/components/GlobalPopup.vue'
import { useSessionStore } from '@/features/session/stores/session'
import ReleaseNotesModal from '@/app/components/ReleaseNotesModal.vue'
import { useReleaseNotesStore } from '@/app/stores/releaseNotes'
import { formatApiError } from '@/shared/api/apiError'
import { createMainMenuOptions, MAIN_MENU_OPTIONS_KEY } from '@/app/services/mainMenu'
import CommandPalette from '@/app/components/navigation/CommandPalette.vue'
import { useProjectCatalogStore } from '@/features/projects/stores/projectCatalog'
import { useMediaQuery } from '@/shared/composables/mediaQuery'

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

.protected-shell,
.protected-main,
.protected-content {
  min-height: 100dvh;
  min-width: 0;
}

.protected-sider {
  height: 100dvh;
  position: sticky;
  top: 0;
}

.protected-content {
  display: flex;
  flex-direction: column;
  padding: var(--app-gutter);
}

.protected-page {
  flex: 1;
  margin-inline: auto;
  max-width: var(--app-content-max-width);
  min-width: 0;
  width: 100%;
}

.protected-footer {
  font-size: 12px;
  margin-top: 20px;
  opacity: 0.72;
}
</style>
