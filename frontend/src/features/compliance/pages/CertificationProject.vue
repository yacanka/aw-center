<script setup lang="ts">
import { computed } from 'vue'
import { useProjectCatalogStore } from '@/features/projects/stores/projectCatalog'
import ComplianceDashboard from '../components/ComplianceDashboard.vue'

const props = defineProps<{ project: string }>()
const catalog = useProjectCatalogStore()
const selected = computed(() =>
  catalog.complianceProjects.find((item) => item.slug === props.project)
)
function load() {
  void catalog.load().catch(() => undefined) // The store exposes the error and retry state.
}
load()
</script>

<template>
  <router-link :to="{ name: 'compdocsHome' }">Proje seçimi</router-link>
  <n-spin v-if="catalog.status === 'loading'" />
  <n-alert v-else-if="catalog.error" type="error">
    {{ catalog.error }} <n-button @click="load">Tekrar dene</n-button>
  </n-alert>
  <template v-else-if="selected">
    <n-flex align="center" justify="space-between" class="project-heading">
      <h1>{{ selected.name }} · Certification Dashboard</h1>
      <router-link
        :to="{ name: 'compdocs', params: { project } }"
        v-slot="{ href, navigate }"
        custom
      >
        <n-button tag="a" type="primary" :href="href" @click="navigate">Proje dokümanları</n-button>
      </router-link>
    </n-flex>
    <ComplianceDashboard :project="project" />
  </template>
  <n-empty v-else description="Bu projeye erişiminiz yok." />
</template>

<style scoped>
.project-heading {
  margin-block: 12px 24px;
}
h1 {
  margin: 0;
  font-size: clamp(1.3rem, 3vw, 2rem);
}
</style>
