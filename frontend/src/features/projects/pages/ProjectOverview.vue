<script setup lang="ts">
import { onMounted, ref } from 'vue'
import {
  NAlert,
  NButton,
  NCard,
  NCollapse,
  NCollapseItem,
  NEmpty,
  NSpace,
  NSpin,
  NTag
} from 'naive-ui'
import {
  fetchProjectOverview,
  fieldLabels,
  statusLabels,
  type ProjectOverview
} from '../api/projectOverview'
import { formatApiError } from '@/shared/api/apiError'

const projects = ref<ProjectOverview[]>([])
const loading = ref(true)
const error = ref('')
const services = { jira: 'JIRA', compliance: 'Uygunluk dokümanları', organization: 'Organizasyon' }

async function load() {
  loading.value = true
  error.value = ''
  try {
    projects.value = await fetchProjectOverview()
  } catch (cause) {
    error.value = formatApiError(cause)
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <n-card title="Projeler">
    <n-spin v-if="loading" aria-label="Projeler yükleniyor" />
    <n-alert v-else-if="error" type="error">
      {{ error }}
      <n-button size="small" @click="load">Tekrar dene</n-button>
    </n-alert>
    <n-empty v-else-if="!projects.length" description="Erişebildiğiniz proje bulunmuyor." />
    <n-collapse v-else>
      <n-collapse-item v-for="project in projects" :key="project.slug" :name="project.slug">
        <template #header>
          <n-space align="center" size="small">
            <strong>{{ project.name }}</strong>
            <code>{{ project.slug }}</code>
            <n-tag v-if="!project.enabled" size="small" type="warning">Devre dışı</n-tag>
            <n-tag v-for="service in project.capabilities" :key="service" size="small">{{
              services[service]
            }}</n-tag>
          </n-space>
        </template>
        <dl>
          <template v-for="service in project.capabilities" :key="service">
            <dt>{{ services[service] }} rolünüz</dt>
            <dd>{{ project.roles[service] || 'Atanmamış' }}</dd>
          </template>
          <template v-if="project.capabilities.includes('jira')">
            <template v-for="(label, key) in fieldLabels" :key="key">
              <dt>{{ label }}</dt>
              <dd v-if="project.configuration[key]">
                {{ statusLabels[project.configuration[key]!.status] }}
                <code v-if="project.configuration[key]!.value !== undefined">{{
                  [project.configuration[key]!.value].flat().join(', ')
                }}</code>
              </dd>
              <dd v-else>Tanımlanmamış</dd>
            </template>
          </template>
          <template v-else>
            <dt>JIRA ve DCC yapılandırması</dt>
            <dd>Uygulanmıyor</dd>
          </template>
        </dl>
      </n-collapse-item>
    </n-collapse>
  </n-card>
</template>

<style scoped>
dl {
  display: grid;
  grid-template-columns: minmax(8rem, 13rem) minmax(0, 1fr);
  gap: 0.5rem 1rem;
}
dd {
  margin: 0;
  overflow-wrap: anywhere;
}
dd code {
  display: block;
}
@media (max-width: 600px) {
  dl {
    grid-template-columns: 1fr;
    gap: 0.15rem;
  }
  dd {
    margin-bottom: 0.6rem;
  }
}
</style>
