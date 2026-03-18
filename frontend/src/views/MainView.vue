<template>
  <ParticleBackground v-if="useUserStore().getPreferences.has_particles" />
  <Welcome v-if="route.path.includes('welcome')" />
  <RouterView v-else-if="route.path.includes('login')" />
  <n-layout v-else-if="!route.path.includes('welcome') && !route.path.includes('login')" has-sider class="transparent">
    <n-layout-sider bordered collapse-mode="width" :collapsed-width="64" :width="240" show-trigger class="transparent">
      <n-menu :options="menuOptions" :value="currentPage" :collapsed-width="64" :collapsed-icon-size="22"
        @update:value="handleMenuSelect" />
    </n-layout-sider>

    <n-layout class="transparent">
      <n-layout-content style="padding: 24px; height: 96vh;" class="transparent">
        <n-scrollbar style="max-width: 99%; margin: 0 auto; padding: 1rem; max-height: 100%">
          <RouterView />
        </n-scrollbar>
      </n-layout-content>
    </n-layout>
    <ReleaseNotesModal />
  </n-layout>
  <Popup />
  <n-p style="position: fixed; left: 8px; bottom: 4px; font-size: 12px;">
    AW Center (v{{ appVersion }}) © 2026
  </n-p>
</template>

<script setup lang="ts">
import { ref, onMounted, h, computed, Component, watch } from 'vue'
import { RouterLink, RouterView, useRouter, useRoute } from 'vue-router'
import { useMessage, useDialog, useNotification, useLoadingBar, NIcon } from 'naive-ui'
import { useCompdocStore, useDccStore, useAuthStore, useDdfStore, useOrgsStore } from '@/stores/api'
import { ArrowReset24Regular, Mail24Regular, ImageMultiple24Regular, PeopleAudience24Regular, ArrowRepeatAll24Regular, Document24Regular, Home24Regular, Book24Regular, Settings24Regular, People24Regular, EyeTracking24Regular, FormNew24Regular, Door20Regular, Glasses24Regular, Edit24Regular, LinkSquare24Regular, Cut24Regular } from '@vicons/fluent';
import { Excel, Word, Pdf } from '@/stores/iconStore'
import ParticleBackground from '@/components/ParticleBackground.vue'
import Welcome from '@/views/Welcome.vue'
import Popup from '@/components/GlobalPopup.vue'
import { useUserStore } from '@/stores/user'
import ReleaseNotesModal from "@/components/ReleaseNotesModal.vue";
import { useReleaseNotesStore } from "@/stores/releaseNotes";

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
const releaseNotes = useReleaseNotesStore();

function handleMenuSelect(key: string, item: any) {
  router.push(key)
};

function renderIcon(iconAsset: Component) {
  return () => h(NIcon, null, { default: () => h(iconAsset) })
}

const menuOptions = [
  { label: "AW Center", key: "/home", name: "aw center", icon: renderIcon(Home24Regular) },
  { key: "divider1", type: "divider" },
  {
    label: "Compliance Docs", key: "/compdocs", name: "projects", icon: renderIcon(Book24Regular), children: [
      { label: "Cover Page Creator", key: "/compdocs/coverpagecreator", name: "coverpagecreator", disabled: false },
      { key: "divider2", type: "divider" },
      {
        label: "Özgür", key: "/ozgurlist", name: "ozgur", children: [
          { label: "AESA", key: "/compdocs/aesa", name: "aesa", disabled: false },
          { label: "HYS", key: "/compdocs/hys", name: "hys", disabled: false },
          { label: "Özgür-1", key: "/compdocs/ozgur", name: "ozgur", disabled: false },
          { label: "Blok 30", key: "/compdocs/blok30", name: "blok30", disabled: false },
          { label: "Blok 40/50", key: "/compdocs/blok4050", name: "blok4050", disabled: true },
        ]
      },
      { label: "Gokbey", key: "/compdocs/gokbey", name: "gokbey", disabled: true },
      { label: "Piku", key: "/compdocs/piku", name: "piku", disabled: false },
      { label: "Havasoj", key: "/compdocs/havasoj", name: "havasoj", disabled: false }
    ]
  },
  { label: "Outlook Task", key: "/outlook", name: "outlook", icon: renderIcon(Mail24Regular), disabled: false },
  { label: "ECR Master", key: "/dcc", name: "dcc", icon: renderIcon(EyeTracking24Regular) },
  {
    label: "DOORS", key: "/doors", name: "doors", icon: renderIcon(Door20Regular), children: [
      { label: "PoC Linker", key: "/doors/poclinker", name: "pocLinker", icon: renderIcon(LinkSquare24Regular) },
      { label: "Agent", key: "/doors/agent", name: "agent", icon: renderIcon(Glasses24Regular), disabled: true },
      { label: "Script Generator", key: "/doors/scripter", name: "scripter", icon: renderIcon(Edit24Regular) },
    ]
  },
  {
    label: "Compare", key: "/compare", name: "compare", icon: renderIcon(ArrowRepeatAll24Regular), children: [
      { label: "Excel", key: "/compare/excel", name: "excel", icon: renderIcon(Excel) },
      { label: "Word", key: "/compare/word", name: "word", icon: renderIcon(Word) },
      { label: "Pdf", key: "/compare/pdf", name: "pdf", icon: renderIcon(Pdf) },
    ]
  },
  {
    label: "Pdf", key: "/pdf", name: "pdf", icon: renderIcon(Pdf), children: [
      { label: "Split", key: "/pdf/split", name: "split", icon: renderIcon(Cut24Regular) },
    ]
  },
  { label: "Translator", key: "/translator", name: "translator", icon: renderIcon(ArrowReset24Regular) },
  { label: "DDF Assistant", key: "/ddfAssistant", name: "ddf", icon: renderIcon(FormNew24Regular) },
  { label: "Powerpoint Gallery", key: "/pptxGallery", name: "pptxgallery", icon: renderIcon(ImageMultiple24Regular) },
  { label: "Organization", key: "/organization", name: "organization", icon: renderIcon(PeopleAudience24Regular) },
  { label: "Users", key: "/users", name: "users", icon: renderIcon(People24Regular) },
  { label: "Settings", key: "/settings", name: "settings", icon: renderIcon(Settings24Regular) }
]

const currentPage = computed(() => route.path)
const userStore = useUserStore()
const appVersion = import.meta.env.VITE_VERSION


onMounted(async () => {
  try {
    await userStore.fetchCurrentUser()
    await releaseNotes.checkUnseen();
  } catch (err) {
    router.push({ name: "login" })
  }
})
</script>