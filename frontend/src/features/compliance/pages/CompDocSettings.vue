<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { onBeforeRouteLeave, onBeforeRouteUpdate, useRoute, useRouter } from 'vue-router'
import { useProjectCatalogStore } from '@/features/projects/stores/projectCatalog'
import { createCompdocController } from '@/features/compliance/composables/compdocController'
import CompDocColumnSettings from '@/features/compliance/components/CompDocColumnSettings.vue'
import {
  createAllColumnSettings,
  createDefaultColumnSettings,
  readCompdocColumnSettings,
  reconcileColumnSettings,
  saveCompdocColumnSettings
} from '@/features/compliance/api/compdocColumns'
import type { IColumnSetting, ICompDocFieldMetadata } from '@/features/compliance/models/compdocs'

const route = useRoute()
const router = useRouter()
const catalog = useProjectCatalogStore()
const project = computed(() => (typeof route.query.project === 'string' ? route.query.project : ''))
const options = computed(() =>
  catalog.complianceProjects.map((item) => ({ label: item.name, value: item.slug }))
)
const canView = computed(
  () =>
    catalog.status === 'ready' && catalog.hasManagementRole(project.value, 'compliance', 'viewer')
)
const fields = ref<ICompDocFieldMetadata[]>([])
const settings = ref<IColumnSetting[]>([])
const schemaVersion = ref(0)
const pageSize = ref(8)
const loading = ref(false)
const error = ref('')
const saved = ref('')
const snapshot = () => JSON.stringify({ settings: settings.value, pageSize: pageSize.value })
const dirty = computed(() => Boolean(saved.value) && saved.value !== snapshot())
let requestId = 0

async function load() {
  const request = ++requestId
  fields.value = []
  settings.value = []
  saved.value = ''
  error.value = ''
  loading.value = false
  if (!canView.value) return
  loading.value = true
  const controller = createCompdocController()
  controller.setProjectName(project.value)
  await controller.fetchCompDocFields()
  if (request !== requestId) return
  loading.value = false
  error.value =
    controller.fieldsError ||
    (!controller.fields.length ? 'No column settings are available for this project.' : '')
  if (error.value) return
  try {
    fields.value = controller.fields
    schemaVersion.value = controller.fieldsSchemaVersion
    settings.value = readCompdocColumnSettings(project.value, fields.value)
    pageSize.value = Math.min(
      200,
      Math.max(1, Number(localStorage.getItem('compdocs>page_size')) || 8)
    )
    saved.value = snapshot()
  } catch {
    error.value = 'Browser storage is unavailable. Enable it and retry to manage your preferences.'
  }
}
function save() {
  if (!canView.value || loading.value || error.value) return
  try {
    settings.value = reconcileColumnSettings(settings.value, fields.value)
    saveCompdocColumnSettings(project.value, schemaVersion.value, settings.value)
    localStorage.setItem('compdocs>page_size', String(pageSize.value))
    saved.value = snapshot()
    window.$message.success('Settings saved.')
  } catch {
    window.$message.error('Settings could not be saved. Check browser storage and try again.')
  }
}
function discard() {
  const previous = JSON.parse(saved.value)
  settings.value = previous.settings
  pageSize.value = previous.pageSize
}
function confirmLeave() {
  return !dirty.value || window.confirm('Discard unsaved compliance document settings?')
}
function beforeUnload(event: BeforeUnloadEvent) {
  if (dirty.value) {
    event.preventDefault()
    event.returnValue = ''
  }
}
window.addEventListener('beforeunload', beforeUnload)
onBeforeUnmount(() => {
  requestId++
  window.removeEventListener('beforeunload', beforeUnload)
})
onBeforeRouteLeave(confirmLeave)
onBeforeRouteUpdate((to) => to.query.project === route.query.project || confirmLeave())
watch([project, canView], load, { immediate: true })
void catalog.load().catch(() => undefined)
</script>

<template>
  <main class="compdoc-settings">
    <header>
      <n-button
        text
        @click="
          router.push(
            canView ? { name: 'compdocs', params: { project } } : { name: 'compdocsHome' }
          )
        "
        >Back to compliance documents</n-button
      >
      <h1>Compliance document settings</h1>
      <n-text depth="3"
        >Customize your document table. Preferences are saved in this browser; they do not change
        documents or other users' settings.</n-text
      >
    </header>
    <n-card title="Project" size="small">
      <n-select
        :value="project || null"
        :options="options"
        :loading="catalog.status === 'loading'"
        placeholder="Select a project"
        aria-label="Project"
        @update:value="router.push({ name: 'compdocsSettings', query: { project: $event } })"
      />
      <n-text depth="3">Column layouts are saved separately for each project.</n-text>
    </n-card>
    <n-alert v-if="catalog.error" type="error"
      >{{ catalog.error }}
      <n-button @click="catalog.load(true).catch(() => undefined)">Retry</n-button></n-alert
    >
    <n-alert v-else-if="project && catalog.status === 'ready' && !canView" type="warning"
      >You do not have permission to view this project's compliance documents.</n-alert
    >
    <n-empty v-else-if="!project" description="Select a project to configure its document table." />
    <n-spin v-else-if="loading" />
    <n-alert v-else-if="error" type="error"
      >{{ error }} <n-button @click="load">Retry</n-button></n-alert
    >
    <template v-else-if="canView && fields.length">
      <n-card title="Table display" size="small">
        <n-form-item label="Rows per page">
          <n-input-number
            :value="pageSize"
            :min="1"
            :max="200"
            :precision="0"
            :show-button="true"
            :update-value-on-input="false"
            :on-update:value="(value: number | null) => (pageSize = value || 8)"
            aria-label="Rows per page"
          />
        </n-form-item>
        <n-text depth="3"
          >Applies to all compliance document tables in this browser. You can also change it from
          the table.</n-text
        >
      </n-card>
      <n-card title="Columns" size="small">
        <n-flex class="presets" justify="space-between" align="center">
          <n-text depth="3"
            >Choose columns, set their order and adjust how values are displayed.</n-text
          >
          <n-space
            ><n-button @click="settings = createDefaultColumnSettings(fields)"
              >Recommended columns</n-button
            ><n-button @click="settings = createAllColumnSettings(fields)"
              >All columns</n-button
            ></n-space
          >
        </n-flex>
        <CompDocColumnSettings v-model:settings="settings" :fields="fields" />
      </n-card>
      <n-card size="small" class="save-bar">
        <n-flex justify="space-between" align="center">
          <n-text depth="3" role="status">{{
            dirty ? 'You have unsaved changes.' : 'All changes saved.'
          }}</n-text>
          <n-space
            ><n-button :disabled="!dirty" @click="discard">Discard changes</n-button
            ><n-button type="primary" :disabled="!dirty" @click="save"
              >Save settings</n-button
            ></n-space
          >
        </n-flex>
      </n-card>
    </template>
  </main>
</template>

<style scoped>
.compdoc-settings {
  max-width: 1080px;
  margin: 0 auto;
  display: grid;
  gap: 20px;
  min-width: 0;
  padding-bottom: 20px;
}
h1 {
  font-size: 26px;
  line-height: 1.3;
  margin: 16px 0 8px;
}
.presets {
  margin-bottom: 20px;
}
.save-bar {
  position: sticky;
  bottom: 12px;
  z-index: 2;
}
@media (max-width: 600px) {
  h1 {
    font-size: 22px;
  }
  .save-bar {
    position: static;
  }
}
</style>
