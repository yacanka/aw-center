<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, shallowRef } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import type { ThemeName } from '@/app/services/theme'
import ComplianceDashboard from '@/features/compliance/components/ComplianceDashboard.vue'
import { formatApiError } from '@/shared/api/apiError'
import { formatTurkishDateTime } from '@/shared/utils/time'
import { readDashboard, readDocuments, readSource, type ViewerSource } from './api'
import ViewerDocuments from './ViewerDocuments.vue'

defineProps<{ themeName: ThemeName }>()
const router = useRouter()
const route = useRoute()
const source = shallowRef<ViewerSource>()
const sourceError = ref('')
const loadingSource = ref(false)
const bootstrap = new AbortController()
const project = computed(() =>
  source.value?.projects.find((item) => item.slug === route.params.project)
)
const projectOptions = computed(
  () => source.value?.projects.map(({ name, slug }) => ({ label: name, value: slug })) || []
)
const viewingDocuments = computed(() => route.name === 'compdocs')

async function selectSource(next: ViewerSource) {
  source.value = next
  if (!project.value && next.projects.length) {
    await router.replace({ name: 'dashboard', params: { project: next.projects[0].slug } })
  }
}

async function initialize(refresh = false) {
  loadingSource.value = true
  sourceError.value = ''
  try {
    const next = await readSource(bootstrap.signal, refresh)
    if (!bootstrap.signal.aborted) await selectSource(next)
  } catch (error) {
    if (!bootstrap.signal.aborted) sourceError.value = formatApiError(error)
  } finally {
    loadingSource.value = false
  }
}

// Publish the new source timestamp together with the successfully loaded project view.
async function loadProject<T>(
  reader: (slug: string, signal: AbortSignal) => Promise<T>,
  slug: string,
  signal: AbortSignal,
  refresh: boolean
): Promise<T> {
  const next = refresh ? await readSource(signal, true) : undefined
  signal.throwIfAborted()
  if (next && !next.projects.some((item) => item.slug === slug)) {
    await selectSource(next)
    throw new Error('Proje güncel kaynakta bulunamadı.')
  }
  const result = await reader(slug, signal)
  signal.throwIfAborted()
  if (next) await selectSource(next)
  return result
}

const loadDashboard = (slug: string, signal: AbortSignal, refresh: boolean) =>
  loadProject(readDashboard, slug, signal, refresh)
const loadDocuments = (slug: string, signal: AbortSignal, refresh: boolean) =>
  loadProject(readDocuments, slug, signal, refresh)

onMounted(() => initialize())
onBeforeUnmount(() => bootstrap.abort())
</script>

<template>
  <main class="viewer">
    <header>
      <n-flex align="center" justify="space-between">
        <h1>Certification Dashboard</h1>
        <n-flex align="center" class="project-controls">
          <label v-if="projectOptions.length" for="viewer-project">Proje</label>
          <n-select
            v-if="projectOptions.length"
            :value="project?.slug"
            :options="projectOptions"
            :input-props="{ id: 'viewer-project', 'aria-label': 'Proje' }"
            @update:value="
              (slug: string) => router.push({ name: route.name!, params: { project: slug } })
            "
          />
          <router-link
            v-if="project"
            custom
            :to="{
              name: viewingDocuments ? 'dashboard' : 'compdocs',
              params: { project: project.slug }
            }"
            v-slot="{ href, navigate }"
          >
            <n-button tag="a" secondary :href="href" @click="navigate">{{
              viewingDocuments ? 'Dashboard' : 'Proje dokümanları'
            }}</n-button>
          </router-link>
        </n-flex>
      </n-flex>
      <n-text v-if="source" depth="3">
        {{ source.source_kind === 'backup' ? 'Yedekten okundu' : 'Yerel SQLite' }} · Son okuma
        {{ formatTurkishDateTime(source.read_at, true) }}
      </n-text>
    </header>
    <n-alert v-if="source?.warning" type="warning">{{ source.warning }}</n-alert>
    <n-alert v-if="sourceError" type="error">{{ sourceError }}</n-alert>
    <n-spin v-if="loadingSource" />
    <template v-else-if="project">
      <ViewerDocuments
        v-if="viewingDocuments"
        :project="project.slug"
        :load-documents="loadDocuments"
      />
      <ComplianceDashboard
        v-else
        :project="project.slug"
        :load-dashboard="loadDashboard"
        :theme-name="themeName"
        keep-last-result
      />
    </template>
    <n-flex v-else align="center">
      <n-text v-if="!sourceError">Kaynakta görüntülenebilecek proje bulunamadı.</n-text>
      <n-button @click="initialize(true)">Yenile</n-button>
    </n-flex>
  </main>
</template>

<style scoped>
.viewer {
  box-sizing: border-box;
  margin: 0 auto;
  max-width: 1600px;
  padding: clamp(12px, 3vw, 40px);
}
header,
.viewer > .n-alert {
  margin-bottom: 16px;
}
h1 {
  margin: 0 0 4px;
  font-size: clamp(1.35rem, 3vw, 2rem);
}
.project-controls {
  max-width: 100%;
}
.project-controls .n-select {
  width: min(220px, 100%);
}
</style>
