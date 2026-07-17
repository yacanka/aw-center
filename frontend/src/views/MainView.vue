<template>
  <ParticleBackground v-if="useUserStore().getPreferences.has_particles" />
  <Welcome v-if="route.path.includes('welcome')" />
  <RouterView v-else-if="route.path.includes('login')" />
  <n-layout
    v-else-if="!route.path.includes('welcome') && !route.path.includes('login')"
    has-sider
    class="transparent"
  >
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
    <ReleaseNotesModal />
  </n-layout>
  <Popup />
  <n-p style="position: fixed; left: 8px; bottom: 4px; font-size: 12px">
    AW Center (v{{ appVersion }}) © 2026
  </n-p>
</template>

<script setup lang="ts">
import { ref, onMounted, h, computed, Component, watch } from 'vue'
import { RouterLink, RouterView, useRouter, useRoute } from 'vue-router'
import { useMessage, useDialog, useNotification, useLoadingBar, NIcon } from 'naive-ui'
import type { MenuOption } from 'naive-ui'
import { useCompdocStore, useDccStore, useAuthStore, useDdfStore, useOrgsStore } from '@/stores/api'
import {
  ArrowReset24Regular,
  Mail24Regular,
  ImageMultiple24Regular,
  PeopleAudience24Regular,
  ArrowRepeatAll24Regular,
  Document24Regular,
  Home24Regular,
  Book24Regular,
  Settings24Regular,
  People24Regular,
  EyeTracking24Regular,
  FormNew24Regular,
  Door20Regular,
  Glasses24Regular,
  Edit24Regular,
  LinkSquare24Regular,
  Cut24Regular,
  Code24Regular
} from '@vicons/fluent'
import { Excel, Word, Pdf } from '@/stores/iconStore'
import ParticleBackground from '@/components/ParticleBackground.vue'
import Welcome from '@/views/Welcome.vue'
import Popup from '@/components/GlobalPopup.vue'
import { useUserStore } from '@/stores/user'
import ReleaseNotesModal from '@/components/ReleaseNotesModal.vue'
import { useReleaseNotesStore } from '@/stores/releaseNotes'
import { PROJECT_REGISTRY_FALLBACK, fetchCompdocProjectRegistry } from '@/services/projectRegistry'
import { formatApiError } from '@/services/apiError'
import type { ProjectRegistryItem } from '@/models/projectRegistry'

window.$loadingBar = useLoadingBar()
window.$notification = useNotification()
window.$dialog = useDialog()
window.$message = useMessage()

window.$compdocStore = useCompdocStore()
window.$dccStore = useDccStore()
window.$authStore = useAuthStore()
window.$ddfStore = useDdfStore()
window.$orgsStore = useOrgsStore()
window.$userStore = useUserStore()

const router = useRouter()
const route = useRoute()
const releaseNotes = useReleaseNotesStore()

function handleMenuSelect(key: string) {
  router.push(key)
}

function renderIcon(iconAsset: Component) {
  return () => h(NIcon, null, { default: () => h(iconAsset) })
}

type ProjectMenuOption = MenuOption & {
  name: string
  children?: ProjectMenuOption[]
}

const projectRegistryItems = ref<ProjectRegistryItem[]>(PROJECT_REGISTRY_FALLBACK)

const projectMenuChildren = computed<ProjectMenuOption[]>(() => {
  const projects = projectRegistryItems.value
  return [
    {
      label: 'Doc Analyzer',
      key: '/compdocs/docAnalyzer',
      name: 'docAnalyzer',
      disabled: false,
      icon: renderIcon(EyeTracking24Regular)
    },
    {
      label: 'Cover Page Creator',
      key: '/compdocs/coverpagecreator',
      name: 'coverpagecreator',
      disabled: false
    },
    { key: 'divider2', type: 'divider', name: 'projectDivider' },
    createOzgurProjectGroup(projects),
    ...projects.filter(isTopLevelProject).map(createProjectMenuOption)
  ]
})

const menuOptions = computed<ProjectMenuOption[]>(() => [
  { label: 'AW Center', key: '/home', name: 'aw center', icon: renderIcon(Home24Regular) },
  { key: 'divider1', type: 'divider', name: 'mainDivider' },
  {
    label: 'Compliance Docs',
    key: '/compdocs',
    name: 'projects',
    icon: renderIcon(Book24Regular),
    children: projectMenuChildren.value
  },
  {
    label: 'Outlook Task',
    key: '/outlook',
    name: 'outlook',
    icon: renderIcon(Mail24Regular),
    disabled: false
  },
  { label: 'ECR Master', key: '/dcc', name: 'dcc', icon: renderIcon(EyeTracking24Regular) },
  {
    label: 'DOORS',
    key: '/doors',
    name: 'doors',
    icon: renderIcon(Door20Regular),
    children: [
      {
        label: 'PoC Linker',
        key: '/doors/poclinker',
        name: 'pocLinker',
        icon: renderIcon(LinkSquare24Regular)
      },
      {
        label: 'Agent',
        key: '/doors/agent',
        name: 'agent',
        icon: renderIcon(Glasses24Regular)
      },
      {
        label: 'Script Generator',
        key: '/doors/scripter',
        name: 'scripter',
        icon: renderIcon(Edit24Regular)
      }
    ]
  },
  {
    label: 'Developer',
    key: '/developer',
    name: 'developer',
    icon: renderIcon(Code24Regular),
    children: [
      {
        label: 'DOORS',
        key: '/developer/doors',
        name: 'developerDoors',
        icon: renderIcon(Door20Regular)
      }
    ]
  },
  {
    label: 'Teamcenter',
    key: '/teamcenter/agent',
    name: 'teamcenter',
    icon: renderIcon(Glasses24Regular)
  },
  {
    label: 'Compare',
    key: '/compare',
    name: 'compare',
    icon: renderIcon(ArrowRepeatAll24Regular),
    children: [
      { label: 'Excel', key: '/compare/excel', name: 'excel', icon: renderIcon(Excel) },
      { label: 'Word', key: '/compare/word', name: 'word', icon: renderIcon(Word) },
      { label: 'Pdf', key: '/compare/pdf', name: 'pdf', icon: renderIcon(Pdf) }
    ]
  },
  {
    label: 'Pdf',
    key: '/pdf',
    name: 'pdf',
    icon: renderIcon(Pdf),
    children: [{ label: 'Split', key: '/pdf/split', name: 'split', icon: renderIcon(Cut24Regular) }]
  },
  {
    label: 'Media Converter',
    key: '/media-converter',
    name: 'mediaConverter',
    icon: renderIcon(ImageMultiple24Regular)
  },
  {
    label: 'Translator',
    key: '/translator',
    name: 'translator',
    icon: renderIcon(ArrowReset24Regular)
  },
  { label: 'DDF Assistant', key: '/ddfAssistant', name: 'ddf', icon: renderIcon(FormNew24Regular) },
  {
    label: 'Powerpoint Gallery',
    key: '/pptxGallery',
    name: 'pptxgallery',
    icon: renderIcon(ImageMultiple24Regular)
  },
  {
    label: 'Organization',
    key: '/organization',
    name: 'organization',
    icon: renderIcon(PeopleAudience24Regular)
  },
  { label: 'Users', key: '/users', name: 'users', icon: renderIcon(People24Regular) },
  { label: 'Settings', key: '/settings', name: 'settings', icon: renderIcon(Settings24Regular) }
])

function createOzgurProjectGroup(projects: ProjectRegistryItem[]): ProjectMenuOption {
  return {
    label: 'Özgür',
    key: '/ozgurlist',
    name: 'ozgur',
    children: projects.filter(isOzgurGroupProject).map(createProjectMenuOption)
  }
}

function createProjectMenuOption(project: ProjectRegistryItem): ProjectMenuOption {
  return {
    label: project.display_name,
    key: `/compdocs/${project.slug}`,
    name: project.slug,
    disabled: !project.enabled
  }
}

function isOzgurGroupProject(project: ProjectRegistryItem): boolean {
  return ['aesa', 'hys', 'ozgur', 'blok30', 'blok4050'].includes(project.slug)
}

function isTopLevelProject(project: ProjectRegistryItem): boolean {
  return !isOzgurGroupProject(project)
}

const currentPage = computed(() => route.path)
const appVersion = import.meta.env.VITE_VERSION

onMounted(async () => {
  await loadProjectRegistry()
  await releaseNotes.checkUnseen()
})

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
