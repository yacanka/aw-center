<template>
  <n-card title="Meeting actions" size="small">
    <n-space vertical>
      <n-alert v-if="error" type="error">{{ error }}</n-alert>
      <n-space v-if="jobId" vertical>
        <router-link :to="{ name: 'jobs', query: { job: jobId } }">Open subtask job</router-link>
        <n-text>{{ jobStatus }}</n-text>
        <n-button
          v-if="jobStatus === 'failed' || jobStatus === 'reconciliation_required'"
          :loading="busy"
          @click="resume"
          >Resume and check existing subtasks</n-button
        >
        <n-button v-else-if="isActiveJobStatus(jobStatus)" :loading="busy" @click="load"
          >Refresh subtask status</n-button
        >
      </n-space>
      <n-button v-else-if="!loaded" :loading="busy" @click="load">Review meeting actions</n-button>
      <template v-else>
        <n-text v-if="!rows.length">No actions were found in the minutes.</n-text>
        <n-card v-for="(row, index) in rows" :key="index" size="small">
          <n-space vertical>
            <n-checkbox v-model:checked="row.enabled"
              >Include action {{ row.source.no || index + 1 }}</n-checkbox
            >
            <template v-if="row.enabled">
              <n-form-item label="Summary"
                ><n-input v-model:value="row.item.summary" maxlength="255"
              /></n-form-item>
              <n-form-item
                :label="
                  'Assignee username' +
                  (row.source.responsible ? ' · ' + row.source.responsible : '')
                "
                ><NSearch v-model:value="row.item.assignee"
              /></n-form-item>
              <n-form-item
                :label="
                  'Due date' +
                  (row.source.due_date ? ' · ' + displayDeadline(row.source.due_date) : '')
                "
              >
                <n-date-picker
                  v-model:formatted-value="row.item.due_date"
                  value-format="yyyy-MM-dd"
                  format="dd.MM.yyyy"
                  clearable
                />
              </n-form-item>
              <n-form-item
                v-for="field in extraFields"
                :key="field.id"
                :label="field.name"
                :required="field.required"
              >
                <JiraFieldInput :field="field" v-model="row.item.fields[field.id]" />
              </n-form-item>
            </template>
          </n-space>
        </n-card>
        <n-popconfirm v-if="rows.length" @positive-click="publish">
          <template #trigger
            ><n-button
              type="primary"
              :loading="busy"
              :disabled="!items.length || items.some((item) => !item.summary.trim())"
              >Create selected subtasks</n-button
            ></template
          >
          Create {{ items.length }} subtasks under the published meeting Task?
        </n-popconfirm>
      </template>
    </n-space>
  </n-card>
</template>
<script setup lang="ts">
import { computed, ref } from 'vue'
import { formatApiError } from '@/shared/api/apiError'
import {
  fetchMeetingActions,
  publishMeetingActions,
  type MinutesAction
} from '../api/meetingMinutes'
import { isActiveJobStatus, type JobStatus } from '@/features/jobs/api/jobs'
import { resumeSubtaskJob, type JiraSubtaskItem } from '../api/jiraSubtasks'
import type { IJiraField } from '../models/jira'
import NSearch from '@/shared/components/NSearch.vue'
import { formatTurkishDate } from '@/shared/utils/time'
import JiraFieldInput from './JiraFieldInput.vue'

const props = defineProps<{ draftId: string }>()
const rows = ref<Array<{ enabled: boolean; source: MinutesAction; item: JiraSubtaskItem }>>([])
const items = computed(() => rows.value.filter((row) => row.enabled).map((row) => row.item))
const loaded = ref(false)
const busy = ref(false)
const jobId = ref('')
const jobStatus = ref<JobStatus>()
const error = ref('')
const extraFields = ref<IJiraField[]>([])
function isoDate(raw: string) {
  const value = raw.trim().replace(/^(\d{2})\.(\d{2})\.(\d{4})$/, '$3-$2-$1')
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return null
  const date = new Date(value)
  return Number.isFinite(date.getTime()) && date.toISOString().startsWith(value) ? value : null
}
function displayDeadline(raw: string) {
  const value = isoDate(raw)
  return value ? formatTurkishDate(value) : raw
}
async function load() {
  busy.value = true
  error.value = ''
  try {
    const result = await fetchMeetingActions(props.draftId)
    if ('job_id' in result) {
      jobId.value = result.job_id
      jobStatus.value = result.status
      return
    }
    extraFields.value = result.fields.filter(
      (field) => !['description', 'assignee', 'duedate'].includes(field.id)
    )
    rows.value = result.actions.map((source) => ({
      source,
      enabled: true,
      item: {
        summary: source.action_item,
        description: [source.no, source.responsible, source.due_date].filter(Boolean).join(' · '),
        assignee: source.assignee || '',
        due_date: isoDate(source.due_date),
        fields: {}
      }
    }))
    loaded.value = true
  } catch (cause) {
    error.value = formatApiError(cause)
  } finally {
    busy.value = false
  }
}
async function resume() {
  if (busy.value || !jobId.value) return
  busy.value = true
  error.value = ''
  try {
    const job = await resumeSubtaskJob(jobId.value, 'meeting-resume-' + jobId.value)
    jobId.value = job.id
    jobStatus.value = job.status
  } catch (cause) {
    error.value = formatApiError(cause)
  } finally {
    busy.value = false
  }
}
async function publish() {
  if (busy.value || jobId.value) return
  busy.value = true
  error.value = ''
  try {
    const job = await publishMeetingActions(props.draftId, items.value)
    jobId.value = job.id
    jobStatus.value = job.status
  } catch (cause) {
    error.value = formatApiError(cause)
  } finally {
    busy.value = false
  }
}
</script>
