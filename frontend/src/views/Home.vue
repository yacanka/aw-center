<template>
  <n-flex justify="center">
    <n-h1 class="gradient-text" style="margin: -12px 0 -18px">
      <strong>{{ appTitle }}</strong>
    </n-h1>
  </n-flex>
  <ActionCenter />
  <JobOverview />
  <n-grid cols="1 l:2" responsive="screen" :x-gap="16" :y-gap="16">
    <n-grid-item>
      <QuickAccess :options="menuOptions" :user-id="userStore.getUser.id" />
    </n-grid-item>
    <n-grid-item>
      <IntegrationExceptions />
    </n-grid-item>
  </n-grid>
</template>

<script setup lang="ts">
import { computed, inject } from 'vue'
import ActionCenter from '@/components/ActionCenter.vue'
import IntegrationExceptions from '@/components/home/IntegrationExceptions.vue'
import JobOverview from '@/components/home/JobOverview.vue'
import QuickAccess from '@/components/home/QuickAccess.vue'
import { MAIN_MENU_OPTIONS_KEY, type ProjectMenuOption } from '@/services/mainMenu'
import { useUserStore } from '@/stores/user'

const appTitle = import.meta.env.VITE_APP_TITLE
const userStore = useUserStore()
const menuOptions = inject(
  MAIN_MENU_OPTIONS_KEY,
  computed<ProjectMenuOption[]>(() => [])
)
</script>
