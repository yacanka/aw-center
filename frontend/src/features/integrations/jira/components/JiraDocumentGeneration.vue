<script setup lang="ts">
import { computed, ref } from 'vue'
import { usePageJob } from '@/features/jobs/composables/usePageJob'
import PageJobStatus from '@/features/jobs/components/PageJobStatus.vue'
import DocumentIssueLookup from './DocumentIssueLookup.vue'
import {
  documentError,
  generateJiraDocument,
  type ResolvedDocumentIssue
} from '../api/documentTemplates'

const issue = ref<ResolvedDocumentIssue | null>(null)
const selection = ref<string | null>(null)
const manual = ref(new Map<string, string>())
const busy = ref(false)
const error = ref('')
const pageJob = usePageJob('document_job')
const { job, cancelling, downloading, errorMessage, active } = pageJob
let attempt: { input: string; key: string } | undefined
const template = computed(() => issue.value?.templates.find((item) => item.id === selection.value))
const templateOptions = computed(
  () => issue.value?.templates.map((item) => ({ label: item.name, value: item.id })) || []
)
const fields = computed(() => new Map(issue.value?.fields.map((field) => [field.id, field])))
const rows = computed(
  () =>
    template.value?.placeholders.map((placeholder) => {
      const mapping = template.value!.mapping
      const fieldId = Object.hasOwn(mapping, placeholder.name)
        ? mapping[placeholder.name]
        : undefined
      const field = fieldId ? fields.value.get(fieldId) : undefined
      return { ...placeholder, fieldId, field }
    }) || []
)

const unavailable = computed(() => rows.value.some((row) => row.fieldId && !row.field?.supported))

function select(id: string | null) {
  selection.value = id
  manual.value.clear()
  error.value = ''
  attempt = undefined
}

function resolved(value: ResolvedDocumentIssue | null) {
  issue.value = value
  select(value?.templates.length === 1 ? value.templates[0].id : null)
}

async function generate() {
  if (!issue.value || !template.value || busy.value || active.value || unavailable.value) return
  const payload = {
    issue: issue.value.issue,
    template_id: template.value.id,
    version: template.value.version,
    manual_values: Object.fromEntries(manual.value)
  }
  const input = JSON.stringify(payload)
  if (attempt?.input !== input) attempt = { input, key: crypto.randomUUID() }
  busy.value = true
  error.value = ''
  try {
    pageJob.setJob(await generateJiraDocument(payload, attempt.key))
    attempt = undefined
  } catch (failure) {
    error.value = documentError(failure)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <n-space vertical size="large">
    <DocumentIssueLookup label="JIRA issue" :disabled="busy" @resolved="resolved" />
    <template v-if="issue">
      <n-text strong
        >{{ issue.issue }} · {{ issue.project_name }} · {{ issue.issue_type_name }}</n-text
      >
      <n-alert v-if="!issue.templates.length" type="info"
        >No active template matches this project and issue type.</n-alert
      >
      <n-form-item v-else-if="issue.templates.length > 1" label="Matching templates">
        <n-select
          :value="selection"
          :input-props="{ 'aria-label': 'Matching templates' }"
          :options="templateOptions"
          placeholder="Choose a template"
          filterable
          :disabled="busy"
          @update:value="select"
        />
      </n-form-item>
      <n-card v-if="template" :title="template.name" size="small" embedded>
        <n-space vertical>
          <n-text depth="3">Document preview · Version {{ template.version }}</n-text>
          <div v-for="row in rows" :key="row.name" class="preview-row">
            <n-text strong>{{ row.name }}</n-text>
            <n-text depth="3">
              · {{ row.count }} {{ row.count === 1 ? 'occurrence' : 'occurrences' }}</n-text
            >
            <template v-if="row.fieldId">
              <div>{{ row.field?.name || row.fieldId }} ({{ row.fieldId }})</div>
              <n-text v-if="!row.field" type="warning"
                >Mapped field unavailable on this issue.</n-text
              >
              <n-text v-else-if="!row.field.supported" type="warning"
                >Unsupported JIRA field value.</n-text
              >
              <div v-else class="preview-value">{{ row.field.value || 'Blank in document' }}</div>
            </template>
            <n-input
              v-else
              type="textarea"
              :autosize="{ minRows: 1, maxRows: 5 }"
              :input-props="{ 'aria-label': 'Manual value for ' + row.name }"
              :value="manual.get(row.name) || ''"
              placeholder="Optional manual value"
              :disabled="busy"
              :maxlength="32768"
              @update:value="(value: string) => manual.set(row.name, value)"
            />
          </div>
          <n-alert v-if="unavailable" type="warning"
            >Ask a template publisher to review the field mappings before generation.</n-alert
          >
          <n-button
            type="primary"
            :loading="busy"
            :disabled="busy || active || unavailable"
            @click="generate"
            >Generate DOCX</n-button
          >
        </n-space>
      </n-card>
    </template>
    <n-alert v-if="error || errorMessage" type="error">{{ error || errorMessage }}</n-alert>
    <PageJobStatus
      :job="job"
      :cancelling="cancelling"
      :downloading="downloading"
      download-label="Download DOCX"
      @cancel="pageJob.cancel"
      @download="pageJob.download"
      @open="pageJob.openJobCenter"
    />
  </n-space>
</template>
<style scoped>
.preview-row {
  overflow-wrap: anywhere;
}
.preview-value {
  white-space: pre-wrap;
}
</style>
