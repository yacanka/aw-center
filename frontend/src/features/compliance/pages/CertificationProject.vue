<script setup lang="ts">
import { computed } from 'vue'
import { ArrowLeft24Regular, Document24Regular } from '@vicons/fluent'
import { useProjectCatalogStore } from '@/features/projects/stores/projectCatalog'
import ComplianceDashboard from '../components/ComplianceDashboard.vue'

const props = defineProps<{ project: string }>()
const catalog = useProjectCatalogStore()
const selected = computed(() =>
  catalog.status === 'ready'
    ? catalog.complianceProjects.find((item) => item.slug === props.project)
    : undefined
)
function load() {
  void catalog.load().catch(() => undefined) // The store exposes the error and retry state.
}
load()
</script>

<template>
  <n-flex align="center" justify="space-between" class="project-heading">
    <h1 v-if="selected">{{ selected.name }} · Certification Dashboard</h1>
    <n-flex align="center" :size="8" class="project-actions">
      <router-link :to="{ name: 'compdocsHome' }" v-slot="{ href, navigate }" custom>
        <n-button tag="a" tertiary :href="href" @click="navigate">
          <template #icon><ArrowLeft24Regular aria-hidden="true" /></template>
          Proje seçimi
        </n-button>
      </router-link>
      <router-link
        v-if="selected"
        :to="{ name: 'compdocs', params: { project } }"
        v-slot="{ href, navigate }"
        custom
      >
        <n-button tag="a" type="primary" secondary :href="href" @click="navigate">
          <template #icon><Document24Regular aria-hidden="true" /></template>
          Proje dokümanları
        </n-button>
      </router-link>
    </n-flex>
  </n-flex>
  <n-spin v-if="catalog.status === 'loading'" />
  <n-alert v-else-if="catalog.error" type="error">
    {{ catalog.error }} <n-button @click="load">Tekrar dene</n-button>
  </n-alert>
  <ComplianceDashboard v-else-if="selected" :project="project" />
  <n-empty v-else description="Bu projeye erişiminiz yok." />
</template>

<style scoped>
.project-heading {
  margin-block-end: 20px;
}
h1 {
  margin: 0;
  font-size: clamp(1.3rem, 3vw, 2rem);
  overflow-wrap: anywhere;
}
@media (max-width: 640px) {
  .project-actions > a {
    min-height: 44px;
    padding-inline: 10px;
  }
}
</style>
