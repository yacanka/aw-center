<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from 'vue'
import type { UploadFileInfo } from 'naive-ui'
import { selectedUploadFile } from '@/shared/utils/uploads'
import JiraConnection from './JiraConnection.vue'
import DocumentIssueLookup from './DocumentIssueLookup.vue'
import {
  documentError,
  inspectDocumentTemplate,
  saveDocumentTemplate,
  type DocumentTemplate,
  type Placeholder,
  type ResolvedDocumentIssue,
  type TemplateChanges
} from '../api/documentTemplates'

const props = defineProps<{ template: DocumentTemplate | null }>()
const emit = defineEmits<{ saved: [template: DocumentTemplate]; cancel: [] }>()
const name = ref(props.template?.name || '')
const file = ref<File | null>(null)
const issue = ref<ResolvedDocumentIssue | null>(null)
const placeholders = ref<Placeholder[]>(props.template?.placeholders || [])
const mapped = ref(new Map(Object.entries(props.template?.mapping || {})))
const inspecting = ref(false)
const validFile = ref(false)
const saving = ref(false)
const error = ref('')
let revision = 0
onBeforeUnmount(() => {
  revision++
})
const currentNames = computed(() => new Set(placeholders.value.map(({ name }) => name)))
const removed = computed(
  () =>
    props.template?.placeholders
      .filter((item) => !currentNames.value.has(item.name))
      .map((item) => item.name) || []
)
const fieldOptions = computed(
  () =>
    issue.value?.fields.map(({ name, id, supported }) => ({
      label: name + ' (' + id + ')' + (supported ? '' : ' · unsupported'),
      value: id,
      disabled: !supported
    })) || []
)
const mapping = computed(() =>
  Object.fromEntries([...mapped.value].filter(([key]) => currentNames.value.has(key)))
)
const missing = computed(() => {
  if (!issue.value) return []
  const supported = new Set(
    issue.value.fields.filter((item) => item.supported).map((item) => item.id)
  )
  return Object.entries(mapping.value)
    .filter(([, id]) => !supported.has(id))
    .map(([name]) => name)
})
const newScope = computed(() =>
  Boolean(
    issue.value &&
    props.template &&
    (issue.value.project_id !== props.template.project_id ||
      issue.value.issue_type_id !== props.template.issue_type_id)
  )
)
const changedMapping = computed(() => {
  const before = props.template?.mapping || {}
  const after = mapping.value
  return (
    Object.keys(before).length !== Object.keys(after).length ||
    Object.entries(after).some(
      ([key, value]) => !Object.hasOwn(before, key) || before[key] !== value
    )
  )
})
const needsIssue = computed(
  () => !props.template || !!file.value || changedMapping.value || newScope.value
)
const canSave = computed(
  () =>
    name.value.trim() &&
    !saving.value &&
    !inspecting.value &&
    (!needsIssue.value || issue.value) &&
    !missing.value.length &&
    (file.value ? validFile.value : props.template) &&
    (needsIssue.value || name.value.trim() !== props.template?.name)
)

async function inspect({ file: upload }: { file: UploadFileInfo }) {
  const selected = selectedUploadFile([upload])
  if (!selected || saving.value) return
  const current = ++revision
  file.value = selected
  validFile.value = false
  inspecting.value = true
  error.value = ''
  placeholders.value = []
  try {
    const result = await inspectDocumentTemplate(selected)
    if (current !== revision) return
    placeholders.value = result
    validFile.value = true
  } catch (failure) {
    if (current === revision) error.value = documentError(failure)
  } finally {
    if (current === revision) inspecting.value = false
  }
}

function selectField(name: string, id: string | null) {
  if (id) mapped.value.set(name, id)
  else mapped.value.delete(name)
}

async function save() {
  if (!canSave.value) return
  const changes: TemplateChanges = { name: name.value.trim() }
  if (file.value) changes.file = file.value
  if (needsIssue.value && issue.value) {
    changes.issue = issue.value.issue
    changes.mapping = mapping.value
  }
  saving.value = true
  error.value = ''
  try {
    emit('saved', await saveDocumentTemplate(props.template, changes))
  } catch (failure) {
    error.value = documentError(failure)
  } finally {
    saving.value = false
  }
}
</script>
<template>
  <n-card :title="template ? 'Edit template' : 'Publish template'" size="small">
    <n-space vertical size="large">
      <n-form-item
        label="Template name"
        :show-feedback="false"
        :label-props="{ for: 'jira-template-name' }"
      >
        <n-input
          v-model:value="name"
          :maxlength="160"
          :disabled="saving"
          :input-props="{ id: 'jira-template-name' }"
        />
      </n-form-item>
      <div>
        <n-upload
          :default-upload="false"
          :show-file-list="false"
          :file-list="[]"
          accept=".docx"
          :disabled="saving"
          @change="inspect"
        >
          <n-button :disabled="saving">{{
            template || file ? 'Replace DOCX' : 'Choose DOCX'
          }}</n-button>
        </n-upload>
        <n-text v-if="file">{{ file.name }} · </n-text>
        <n-text depth="3"
          >Use <span v-pre>{{Field name}}</span> for each placeholder in your Word document.</n-text
        >
      </div>
      <JiraConnection
        ><DocumentIssueLookup
          label="Example JIRA issue"
          :disabled="saving"
          @resolved="issue = $event"
      /></JiraConnection>
      <n-text v-if="issue || template">
        {{ (issue || template)?.project_name }} · {{ (issue || template)?.issue_type_name }}
      </n-text>
      <n-alert v-if="newScope" type="warning"
        >Saving will move this template to the example issue’s project and issue type.</n-alert
      >
      <n-spin v-if="inspecting" />
      <n-alert v-if="validFile && removed.length" type="warning"
        >Placeholders removed by the replacement: {{ removed.join(', ') }}</n-alert
      >
      <n-alert v-if="missing.length" type="warning"
        >Choose another field or use manual entry for these unavailable mappings:
        {{ missing.join(', ') }}</n-alert
      >
      <div v-if="placeholders.length">
        <n-h3>Field mappings</n-h3>
        <n-text depth="3"
          >Leave the field empty for optional manual entry during generation.</n-text
        >
        <n-form-item
          v-for="item in placeholders"
          :key="item.name"
          :label="
            item.name + ' · ' + item.count + (item.count === 1 ? ' occurrence' : ' occurrences')
          "
        >
          <div class="mapping">
            <n-select
              :value="mapped.get(item.name) || null"
              :input-props="{ 'aria-label': 'Field for ' + item.name }"
              :disabled="!issue || saving"
              :options="fieldOptions"
              clearable
              filterable
              placeholder="Manual entry"
              @update:value="(id: string | null) => selectField(item.name, id)"
            />
            <n-text v-if="mapped.has(item.name) && issue" depth="3">
              {{
                issue.fields.find((field) => field.id === mapped.get(item.name))?.value ||
                'Blank in example'
              }}
            </n-text>
          </div>
        </n-form-item>
      </div>
      <n-alert v-if="error" type="error">{{ error }}</n-alert>
      <n-flex justify="end">
        <n-button :disabled="saving" @click="emit('cancel')">Cancel</n-button>
        <n-button type="primary" :disabled="!canSave" :loading="saving" @click="save">{{
          template ? 'Save changes' : 'Publish template'
        }}</n-button>
      </n-flex>
    </n-space>
  </n-card>
</template>
<style scoped>
.mapping {
  width: 100%;
  min-width: 0;
  overflow-wrap: anywhere;
  white-space: pre-wrap;
}
</style>
