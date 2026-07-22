<template>
  <ParticleBackground v-if="useUserStore().getPreferences.has_particles" />
  <Welcome v-if="route.path.includes('welcome')" />
  <RouterView v-else-if="isPublicPage" />
  <n-layout v-else-if="!route.path.includes('welcome')" has-sider class="transparent">
    <n-layout-sider
      bordered
      collapse-mode="width"
      :collapsed-width="64"
      :width="240"
      show-trigger
      class="transparent"
    >
      <n-menu
        :options="menuOptions"
        :value="currentPage"
        :collapsed-width="64"
        :collapsed-icon-size="22"
        @update:value="handleMenuSelect"
      />
    </n-layout-sider>

    <n-layout class="transparent">
      <n-layout-content style="padding: 24px; height: 96vh" class="transparent">
        <n-scrollbar style="max-width: 99%; margin: 0 auto; padding: 1rem; max-height: 100%">
          <RouterView />
        </n-scrollbar>
      </n-layout-content>
    </n-layout>
    <CommandPalette :options="menuOptions" />
    <ReleaseNotesModal />
  </n-layout>
  <Popup />
  <n-p style="position: fixed; left: 8px; bottom: 4px; font-size: 12px">
    AW Center (v{{ appVersion }}) © 2026
  </n-p>
</template>

<script setup lang="ts">
import { ref, computed, provide, watch } from 'vue'
import { RouterLink, RouterView, useRouter, useRoute } from 'vue-router'
import { useMessage, useDialog, useNotification, useLoadingBar } from 'naive-ui'
import { useAuthStore } from '@/stores/auth'
import { useCompdocStore } from '@/stores/compdoc'
import { useDccStore } from '@/stores/dcc'
import { useDdfStore } from '@/stores/ddf'
import { useOrgsStore } from '@/stores/organizations'
import ParticleBackground from '@/components/ParticleBackground.vue'
import Welcome from '@/views/Welcome.vue'
import Popup from '@/components/GlobalPopup.vue'
import { useUserStore } from '@/stores/user'
import ReleaseNotesModal from '@/components/ReleaseNotesModal.vue'
import { useReleaseNotesStore } from '@/stores/releaseNotes'
import { PROJECT_REGISTRY_FALLBACK, fetchCompdocProjectRegistry } from '@/services/projectRegistry'
import { formatApiError } from '@/services/apiError'
import type { ProjectRegistryItem } from '@/models/projectRegistry'
import { createMainMenuOptions, MAIN_MENU_OPTIONS_KEY } from '@/services/mainMenu'
import CommandPalette from '@/components/navigation/CommandPalette.vue'

window.$loadingBar = useLoadingBar()
window.$notification = useNotification()
window.$dialog = useDialog()
window.$message = useMessage()

window.$compdocStore = useCompdocStore()
window.$dccStore = useDccStore()
window.$authStore = useAuthStore()
window.$ddfStore = useDdfStore()
window.$orgsStore = useOrgsStore()
const userStore = useUserStore()
window.$userStore = userStore

const router = useRouter()
const route = useRoute()
const releaseNotes = useReleaseNotesStore()

function handleMenuSelect(key: string) {
  router.push(key)
}

const projectRegistryItems = ref<ProjectRegistryItem[]>(PROJECT_REGISTRY_FALLBACK)
const menuOptions = computed(() =>
  createMainMenuOptions(projectRegistryItems.value, userStore.getUser)
)
provide(MAIN_MENU_OPTIONS_KEY, menuOptions)

const currentPage = computed(() => route.path)
const isPublicPage = computed(() => route.meta.public === true)
const appVersion = import.meta.env.VITE_VERSION

const authenticatedShellLoaded = ref(false)

async function initializeAuthenticatedShell() {
  if (authenticatedShellLoaded.value || !userStore.getUser.id) return
  authenticatedShellLoaded.value = true
  await loadProjectRegistry()
  await releaseNotes.checkUnseen()
}

watch(
  () => userStore.getUser.id,
  () => void initializeAuthenticatedShell(),
  { immediate: true }
)

async function loadProjectRegistry() {
  try {
    projectRegistryItems.value = await fetchCompdocProjectRegistry()
  } catch (error) {
    window.$message.warning(`Project list could not be refreshed: ${formatApiError(error)}`)
  }
}
</script>

<style scoped>
.transparent {
  background-color: transparent !important;
}
</style>
