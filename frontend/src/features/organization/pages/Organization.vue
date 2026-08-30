<script setup lang="ts">
import { computed, ref, onMounted } from 'vue'

import People from '@/features/organization/pages/People.vue'
import Responsibles from '@/features/organization/pages/Responsibles.vue'
import Panels from '@/features/organization/pages/Panels.vue'
import Projects from '@/features/organization/pages/Projects.vue'
import Unauthorized from '@/features/session/pages/Unauthorized.vue'
import { useProjectCatalogStore } from '@/features/projects/stores/projectCatalog'
import { provideOrganizationController } from '@/features/organization/composables/organizationController'
import { useMediaQuery } from '@/shared/composables/mediaQuery'

const projectCatalog = useProjectCatalogStore()
provideOrganizationController()
const activeTab = ref('people')
const initializing = ref(true)
const compactTabs = useMediaQuery('(max-width: 900px)')
const tabPlacement = computed(() => (compactTabs.value ? 'top' : 'left'))
const canAccessOrganization = computed(() => projectCatalog.hasAnyRole('organization'))

onMounted(async () => {
  try {
    await projectCatalog.load()
    if (canAccessOrganization.value) {
      const savedTab = localStorage.getItem('orgActiveTab')
      activeTab.value = ['people', 'responsibles', 'panels', 'project'].includes(savedTab || '')
        ? savedTab!
        : 'people'
    }
  } catch {
    // The catalog store owns the sanitized error; project features stay closed.
  } finally {
    initializing.value = false
  }
})

const handleTabChange = (tab: string) => {
  localStorage.setItem('orgActiveTab', tab)
  activeTab.value = tab
}
</script>

<template>
  <n-spin v-if="initializing" size="small" />
  <n-result
    v-else-if="projectCatalog.status === 'error'"
    status="warning"
    title="Project catalog unavailable"
    description="Organization data remains disabled until project roles can be verified."
  />
  <div v-else-if="canAccessOrganization">
    <n-tabs :placement="tabPlacement" v-model:value="activeTab" @update:value="handleTabChange">
      <n-tab-pane name="people" tab="People">
        <People />
      </n-tab-pane>
      <n-tab-pane name="responsibles" tab="Responsibles">
        <Responsibles />
      </n-tab-pane>
      <n-tab-pane name="panels" tab="Panels">
        <Panels />
      </n-tab-pane>
      <n-tab-pane name="project" tab="Projects">
        <Projects />
      </n-tab-pane>
    </n-tabs>
  </div>
  <Unauthorized v-else />
</template>
