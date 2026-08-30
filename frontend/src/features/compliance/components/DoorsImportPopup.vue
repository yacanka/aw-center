<template>
  <n-modal
    v-model:show="show"
    preset="card"
    title="Import from DOORS"
    :mask-closable="!busy"
    class="app-modal app-modal--large"
  >
    <n-space vertical size="large">
      <n-alert type="info" :bordered="false">
        The module is read by the existing Windows DOORS bridge. Data is validated with the same
        identity, required-field, project, version, and concurrency checks as Excel imports.
      </n-alert>

      <n-form-item label="DOORS module path">
        <n-input
          v-model:value="modulePath"
          :disabled="busy"
          placeholder="/Project/Folder/Module"
          @update:value="clearLoadedSource"
        />
      </n-form-item>
      <n-space>
        <n-button
          type="primary"
          :loading="loadingSource"
          :disabled="!modulePath.trim() || busy"
          @click="loadModule"
        >
          Load module fields
        </n-button>
        <n-text v-if="job" depth="3"> Bridge job: {{ job.status }} · {{ job.progress }}% </n-text>
      </n-space>

      <template v-if="source">
        <n-alert type="success" :bordered="false">
          {{ source.row_count }} objects and {{ source.columns.length }} fields loaded from
          {{ source.module_path }}. The last successful mapping is selected when available.
        </n-alert>

        <n-data-table
          :columns="linkColumns"
          :data="linkRows"
          :pagination="false"
          :scroll-x="660"
          size="small"
        />
        <n-alert v-if="mappingProblem" type="warning">{{ mappingProblem }}</n-alert>

        <n-space justify="end">
          <n-button
            type="primary"
            :loading="previewing"
            :disabled="Boolean(mappingProblem) || busy"
            @click="loadPreview"
          >
            Validate import
          </n-button>
        </n-space>
      </template>

      <template v-if="preview">
        <n-divider />
        <n-alert type="info" :bordered="false">
          Review the shared compliance validation result. Confirmation is bound to this DOORS
          artifact, field mapping, user, project, and current database state.
        </n-alert>
        <n-alert v-if="previewNotice" type="warning" style="margin-top: 12px">
          {{ previewNotice }}
        </n-alert>
        <n-space style="margin: 12px 0">
          <n-tag type="success">Create: {{ preview.created_count }}</n-tag>
          <n-tag type="warning">Update: {{ preview.updated_count }}</n-tag>
          <n-tag>Unchanged: {{ preview.unchanged_count }}</n-tag>
          <n-tag :type="preview.rejected_count ? 'error' : 'default'">
            Reject: {{ preview.rejected_count }}
          </n-tag>
        </n-space>
        <n-data-table
          v-if="preview.invalid_documents.length"
          :columns="validationColumns"
          :data="preview.invalid_documents"
          :scroll-x="760"
          size="small"
        />
        <n-space justify="end" style="margin-top: 16px">
          <n-button :disabled="busy" @click="preview = null">Back to mapping</n-button>
          <n-button type="primary" :loading="confirming" :disabled="busy" @click="confirmImport">
            Confirm import
          </n-button>
        </n-space>
      </template>
    </n-space>
  </n-modal>
</template>

<script setup lang="ts">
import { computed, h, ref } from 'vue'
import { NSelect, type DataTableColumns } from 'naive-ui'
import { formatApiError, getApiErrorCode } from '@/shared/api/apiError'
import { enqueueDoorsModuleExport } from '@/features/integrations/api/doorsAutomation'
import { fetchJob, isActiveJobStatus, type Job } from '@/features/jobs/api/jobs'
import {
  confirmDoorsImport,
  fetchDoorsImportSource,
  previewDoorsImport,
  type DoorsImportPreview,
  type DoorsImportSource,
  type ImportInvalidDocument
} from '@/features/compliance/api/compdocImports'
import { useCompdocController } from '@/features/compliance/composables/compdocController'

interface LinkRow {
  source: string
  target: string | null
}

const props = defineProps<{ collectionPath: string }>()
const store = useCompdocController()
const show = ref(false)
const modulePath = ref('')
const job = ref<Job | null>(null)
const source = ref<DoorsImportSource | null>(null)
const mapping = ref<Record<string, string | null>>({})
const preview = ref<DoorsImportPreview | null>(null)
const previewNotice = ref('')
const loadingSource = ref(false)
const previewing = ref(false)
const confirming = ref(false)
const busy = computed(() => loadingSource.value || previewing.value || confirming.value)
const linkRows = computed<LinkRow[]>(() =>
  (source.value?.columns || []).map((column) => ({
    source: column,
    target: mapping.value[column] || null
  }))
)
const selectedTargets = computed(() => Object.values(mapping.value).filter(Boolean))
const mappingProblem = computed(() => {
  if (!source.value) return ''
  const duplicates = selectedTargets.value.filter(
    (target, index, values) => values.indexOf(target) !== index
  )
  if (duplicates.length) return 'Each compliance field can be linked only once.'
  const required = source.value.target_fields
    .filter((field) => field.required)
    .map((field) => field.key)
  const missing = required.filter((field) => !selectedTargets.value.includes(field))
  return missing.length ? `Link required fields: ${missing.join(', ')}` : ''
})

const linkColumns: DataTableColumns<LinkRow> = [
  { title: 'DOORS field', key: 'source' },
  {
    title: 'Compliance field',
    key: 'target',
    render(row) {
      return h(NSelect, {
        value: row.target,
        clearable: true,
        filterable: true,
        placeholder: 'Ignore this field',
        options: (source.value?.target_fields || []).map((field) => ({
          label: `${field.label}${field.required ? ' (required)' : ''}`,
          value: field.key
        })),
        'onUpdate:value': (value: string | null) => {
          mapping.value[row.source] = value
          preview.value = null
        }
      })
    }
  }
]
const validationColumns: DataTableColumns<ImportInvalidDocument> = [
  { title: 'DOORS object row', key: 'row' },
  { title: 'Code', key: 'code' },
  {
    title: 'Validation error',
    key: 'fields',
    render: (row) => JSON.stringify(row.fields)
  }
]

function setActive(active: boolean) {
  show.value = active
  if (!active && !busy.value) reset()
}

function clearLoadedSource() {
  source.value = null
  mapping.value = {}
  preview.value = null
  job.value = null
}

async function loadModule() {
  const path = modulePath.value.trim()
  if (!path || loadingSource.value) return
  loadingSource.value = true
  preview.value = null
  source.value = null
  try {
    job.value = await enqueueDoorsModuleExport(path, 10000, crypto.randomUUID())
    await waitForJob()
    if (!job.value || job.value.status !== 'succeeded') {
      throw new Error(job.value?.recovery_hint || job.value?.message || 'DOORS export failed.')
    }
    source.value = await fetchDoorsImportSource(props.collectionPath, job.value.id)
    mapping.value = Object.fromEntries(
      source.value.columns.map((column) => [column, source.value?.default_mapping[column] || null])
    )
  } catch (error) {
    window.$notification.error({
      title: 'DOORS module could not be loaded',
      description: formatApiError(error)
    })
  } finally {
    loadingSource.value = false
  }
}

async function waitForJob() {
  for (
    let attempt = 0;
    attempt < 240 && job.value && isActiveJobStatus(job.value.status);
    attempt += 1
  ) {
    await delay(1500)
    job.value = await fetchJob(job.value.id)
  }
}

async function loadPreview(refreshed = false) {
  if (!source.value || !job.value || mappingProblem.value) return
  previewing.value = true
  try {
    preview.value = await previewDoorsImport(props.collectionPath, job.value.id, activeMapping())
    previewNotice.value = refreshed
      ? 'Database records changed after your review. The preview was refreshed; review it again.'
      : ''
  } catch (error) {
    window.$notification.error({
      title: 'DOORS import validation failed',
      description: formatApiError(error)
    })
  } finally {
    previewing.value = false
  }
}

async function confirmImport() {
  if (!job.value || !preview.value) return
  confirming.value = true
  try {
    const result = await confirmDoorsImport(
      props.collectionPath,
      job.value.id,
      activeMapping(),
      preview.value.confirmation_token
    )
    window.$notification.success({ title: 'Success', description: result.detail, duration: 3000 })
    await store.fetchCompdocs()
    show.value = false
    reset()
  } catch (error) {
    if (
      ['VERSION_CONFLICT', 'COMPDOC_IMPORT_PREVIEW_EXPIRED'].includes(getApiErrorCode(error) || '')
    ) {
      await loadPreview(true)
    } else {
      window.$notification.error({
        title: 'DOORS import failed',
        description: formatApiError(error)
      })
    }
  } finally {
    confirming.value = false
  }
}

function activeMapping(): Record<string, string> {
  return Object.fromEntries(
    Object.entries(mapping.value).filter((entry): entry is [string, string] => Boolean(entry[1]))
  )
}

function reset() {
  modulePath.value = ''
  clearLoadedSource()
  previewNotice.value = ''
}

function delay(milliseconds: number) {
  return new Promise((resolve) => window.setTimeout(resolve, milliseconds))
}

defineExpose({ setActive })
</script>
