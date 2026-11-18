<script setup lang="ts">
import { computed, ref, onMounted } from 'vue'
import { useSessionStore } from '@/features/session/stores/session'
import DocumentTemplateEditor from './DocumentTemplateEditor.vue'
import {
  documentError,
  downloadDocumentTemplate,
  listDocumentTemplates,
  getDocumentTemplate,
  saveDocumentTemplate,
  type DocumentTemplate
} from '../api/documentTemplates'

const session = useSessionStore()
const publisher = computed(() =>
  session.hasEffectiveRole('integrations', 'manage_jira_document_templates')
)
const templates = ref<DocumentTemplate[]>([])
const edit = ref<DocumentTemplate | null>(null)
const editing = ref(false)
const loading = ref(false)
const busy = ref(false)
const error = ref('')
const query = ref('')
const filtered = computed(() =>
  templates.value.filter((item) =>
    [item.name, item.project_name, item.issue_type_name].some((text) =>
      text.toLowerCase().includes(query.value.trim().toLowerCase())
    )
  )
)

async function load() {
  loading.value = true
  error.value = ''
  try {
    templates.value = await listDocumentTemplates()
  } catch (failure) {
    error.value = documentError(failure)
  } finally {
    loading.value = false
  }
}

async function action(callback: () => Promise<void>) {
  if (busy.value) return
  busy.value = true
  error.value = ''
  try {
    await callback()
  } catch (failure) {
    error.value = documentError(failure)
  } finally {
    busy.value = false
  }
}

function open(template?: DocumentTemplate) {
  return action(async () => {
    edit.value = template ? await getDocumentTemplate(template.id) : null
    editing.value = true
  })
}

function updated(template: DocumentTemplate) {
  const index = templates.value.findIndex((item) => item.id === template.id)
  if (index < 0) templates.value.unshift(template)
  else templates.value.splice(index, 1, template)
  editing.value = false
}

function toggleArchive(template: DocumentTemplate) {
  return action(async () =>
    updated(await saveDocumentTemplate(template, { archived: !template.archived }))
  )
}

onMounted(load)
</script>
<template>
  <DocumentTemplateEditor
    v-if="editing && publisher"
    :template="edit"
    @cancel="editing = false"
    @saved="updated"
  />
  <n-space v-else vertical>
    <n-flex justify="space-between">
      <n-input
        v-model:value="query"
        aria-label="Filter templates"
        placeholder="Search by name, project or issue type"
        clearable
        class="template-search"
      />
      <n-button v-if="publisher" type="primary" :disabled="busy || loading" @click="open()"
        >New template</n-button
      >
    </n-flex>
    <n-alert v-if="error" type="error"
      >{{ error }} <n-button text @click="load">Refresh library</n-button></n-alert
    >
    <n-spin v-if="loading" />
    <n-empty
      v-else-if="!filtered.length && !error"
      :description="query ? 'No templates match your search.' : 'No published templates.'"
    />
    <n-card
      v-for="template in filtered"
      :key="template.id"
      size="small"
      :title="template.name"
      embedded
    >
      <n-space vertical>
        <n-flex align="center">
          <n-text
            >{{ template.project_name }} · {{ template.issue_type_name }} · Version
            {{ template.version }}</n-text
          >
          <n-tag v-if="template.archived" size="small">Archived</n-tag>
        </n-flex>
        <n-flex v-if="publisher">
          <n-button size="small" :disabled="busy" @click="open(template)">Edit template</n-button>
          <n-button
            size="small"
            :disabled="busy"
            @click="action(() => downloadDocumentTemplate(template))"
            >Download source</n-button
          >
          <n-popconfirm @positive-click="toggleArchive(template)">
            <template #trigger
              ><n-button size="small" :disabled="busy">{{
                template.archived ? 'Restore' : 'Archive'
              }}</n-button></template
            >
            {{
              template.archived
                ? 'Make this template available for generation?'
                : 'Archive this template and remove it from generation?'
            }}
          </n-popconfirm>
        </n-flex>
      </n-space>
    </n-card>
  </n-space>
</template>
<style scoped>
.template-search {
  width: min(100%, 26rem);
}
</style>
