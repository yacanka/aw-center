<script setup lang="ts">
import { computed, h, ref, shallowRef, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { NButton, NInput, NModal, type DataTableColumns } from 'naive-ui'
import { compdocDashboardFilters } from '@/features/compliance/api/compdocQuickFilters'
import { humanizeCompdocStatus } from '@/features/compliance/api/compdocWorkspace'
import { formatApiError } from '@/shared/api/apiError'
import { formatTurkishDate } from '@/shared/utils/time'
import type { ViewerDocument } from './api'

const props = defineProps<{
  project: string
  loadDocuments: (
    project: string,
    signal: AbortSignal,
    refresh: boolean
  ) => Promise<ViewerDocument[]>
}>()
const route = useRoute()
const router = useRouter()
const documents = shallowRef<ViewerDocument[]>([])
const search = ref('')
const loading = ref(false)
const error = ref('')
const revision = ref(0)
watch(
  [() => props.project, revision],
  async ([project, refresh], previous, onCleanup) => {
    const controller = new AbortController()
    onCleanup(() => controller.abort())
    if (project !== previous?.[0]) {
      documents.value = []
      search.value = ''
    }
    loading.value = true
    error.value = ''
    try {
      const rows = await props.loadDocuments(
        project,
        controller.signal,
        refresh !== (previous?.[1] ?? 0)
      )
      if (!controller.signal.aborted) documents.value = rows
    } catch (cause) {
      if (!controller.signal.aborted) error.value = formatApiError(cause)
    } finally {
      if (!controller.signal.aborted) loading.value = false
    }
  },
  { immediate: true }
)

const filters = computed(() => compdocDashboardFilters(route.query))
const scoped = computed(() => {
  const { dashboard_delivery, dashboard_cat, dashboard_panel, dashboard_panel_id } = filters.value
  const term = search.value.trim().toLocaleLowerCase('tr')
  return documents.value.filter(
    (row) =>
      (dashboard_delivery === undefined || row.delivery_bucket === dashboard_delivery) &&
      (dashboard_cat === undefined || row.trimmed_cat === dashboard_cat) &&
      (dashboard_panel === undefined || row.panel === dashboard_panel) &&
      (dashboard_panel_id === undefined || row.panel_id === dashboard_panel_id) &&
      (!term ||
        [row.name, row.number].some((value) => value?.toLocaleLowerCase('tr').includes(term)))
  )
})
const scopeLabels = computed(() => {
  const f = filters.value
  return [
    f.dashboard_delivery &&
      humanizeCompdocStatus(f.dashboard_delivery.replace(/^issued:/, 'Issued · ')),
    f.dashboard_cat !== undefined && `CAT · ${f.dashboard_cat || 'Unspecified'}`,
    f.dashboard_panel && `Panel · ${f.dashboard_panel}`,
    f.dashboard_panel_id &&
      (documents.value.find((row) => row.panel_id === f.dashboard_panel_id)?.ata || 'Unassigned')
  ].filter(Boolean)
})
const selected = computed(() => documents.value.find((row) => row.id === route.query.document))
const columns: DataTableColumns<ViewerDocument> = [
  {
    title: 'Doküman',
    key: 'name',
    minWidth: 220,
    render: (row) =>
      h(
        NButton,
        { text: true, type: 'primary', onClick: () => openDocument(row.id) },
        () => row.name
      )
  },
  { title: 'Numara', key: 'number' },
  { title: 'Durum', key: 'status', render: (row) => humanizeCompdocStatus(row.status) },
  { title: 'Panel', key: 'panel' },
  { title: 'ATA', key: 'ata' },
  { title: 'CAT', key: 'cat' },
  { title: 'MoC', key: 'moc' }
]
const fields: Array<[keyof ViewerDocument, string]> = [
  ['number', 'Numara'],
  ['issue', 'Issue'],
  ['status', 'Durum'],
  ['panel', 'Panel'],
  ['ata', 'ATA'],
  ['cat', 'CAT'],
  ['moc', 'MoC'],
  ['cover_page_no', 'Kapak numarası'],
  ['cover_page_issue', 'Kapak issue'],
  ['target_date', 'Hedef tarih'],
  ['revised_target_date', 'Revize hedef tarih'],
  ['release_date', 'Yayın tarihi'],
  ['next_action_due_date', 'Sonraki aksiyon tarihi']
]
function displayField(row: ViewerDocument, key: keyof ViewerDocument) {
  if (key.endsWith('_date')) return formatTurkishDate(row[key])
  if (key === 'status') return humanizeCompdocStatus(row.status)
  return row[key] || '—'
}
function openDocument(id: string) {
  void router.push({ query: { ...route.query, document: id } })
}
function closeDocument() {
  void router.replace({ query: { ...route.query, document: undefined } })
}
</script>

<template>
  <n-card title="Proje dokümanları">
    <template #header-extra
      ><n-button :loading="loading" @click="revision++">Yenile</n-button></template
    >
    <n-alert
      v-if="error"
      type="error"
      :title="documents.length ? 'Son başarılı okumadaki dokümanlar gösteriliyor' : undefined"
      >{{ error }}</n-alert
    >
    <n-alert v-if="route.query.document && !selected && !loading && !error" type="info"
      >Seçilen doküman bu projede bulunamadı.</n-alert
    >
    <n-flex class="tools" align="center">
      <NInput
        v-model:value="search"
        clearable
        placeholder="Ad veya numara ara"
        aria-label="Ad veya numara ara"
      />
      <n-text>{{ scoped.length }} doküman</n-text>
      <n-tag v-if="scopeLabels.length" closable @close="router.replace({ query: {} })">{{
        scopeLabels.join(' · ')
      }}</n-tag>
    </n-flex>
    <n-data-table
      :data="scoped"
      :columns="columns"
      :loading="loading"
      :row-key="(row: ViewerDocument) => row.id"
      :scroll-x="840"
      :pagination="{ pageSize: 25 }"
      size="small"
      striped
    />
    <NModal
      :show="!!selected"
      preset="card"
      :title="selected?.name"
      class="document-modal"
      :style="{ width: 'min(600px, calc(100vw - 24px))' }"
      @update:show="
        (value) => {
          if (!value) closeDocument()
        }
      "
    >
      <dl v-if="selected">
        <template v-for="[key, label] in fields" :key="key">
          <dt>{{ label }}</dt>
          <dd>{{ displayField(selected, key) }}</dd>
        </template>
      </dl>
    </NModal>
  </n-card>
</template>

<style scoped>
.tools {
  margin: 12px 0;
}
.tools .n-input {
  width: min(100%, 300px);
}
dl {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1.3fr);
  gap: 8px 12px;
  margin: 0;
}
dd {
  margin: 0;
  overflow-wrap: anywhere;
  font-weight: 600;
}
</style>
