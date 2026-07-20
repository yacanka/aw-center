<template>
  <n-flex justify="center">
    <n-card title="JIRA DCC Creator" style="width: min(960px, 96vw)">
      <n-space vertical size="large">
        <n-alert type="info" :bordered="false">
          JIRA is read once with the temporary session below. The credential is never stored; the
          captured source and generated DOCX remain private in Job Center.
        </n-alert>
        <n-form label-placement="top" @submit.prevent="previewDcc">
          <n-grid cols="1 700:6" x-gap="12">
            <n-form-item-gi span="1 700:4" label="JIRA task URL or issue key">
              <n-input v-model:value="generator.url" placeholder="DCC-123 or JIRA browse URL" />
            </n-form-item-gi>
            <n-form-item-gi span="1 700:2" label="Temporary JSESSIONID">
              <n-input
                v-model:value="generator.JSESSIONID"
                type="password"
                show-password-on="click"
                :input-props="{
                  autocomplete: 'one-time-code',
                  name: 'temporary-jira-session'
                }"
                placeholder="Not stored"
              />
            </n-form-item-gi>
          </n-grid>
          <n-space justify="end">
            <n-button
              attr-type="submit"
              type="primary"
              :loading="submitting"
              :disabled="!canSubmit"
            >
              Review immutable snapshot
            </n-button>
          </n-space>
        </n-form>

        <n-alert v-if="errorMessage" type="error" closable @close="errorMessage = ''">
          {{ errorMessage }}
        </n-alert>

        <DccCreationPreview
          v-if="currentJob"
          :job="currentJob"
          :confirming="confirming"
          @confirm="confirmPreview"
        />
        <DccJobStatus
          v-if="currentJob"
          :job="currentJob"
          :retrying="retrying"
          :downloading="downloading"
          @open="openJobCenter"
          @retry="retryCurrentJob"
          @download="downloadCurrentJob"
        />
      </n-space>
    </n-card>
  </n-flex>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import DccCreationPreview from '@/components/dcc/DccCreationPreview.vue'
import DccJobStatus from '@/components/dcc/DccJobStatus.vue'
import { formatApiError } from '@/services/apiError'
import {
  confirmDccDocumentJob,
  downloadJob,
  fetchJob,
  previewDccDocumentJob,
  retryJob,
  type Job
} from '@/services/jobs'

const route = useRoute()
const router = useRouter()
const generator = reactive({ JSESSIONID: '', url: '' })
const currentJob = ref<Job | null>(null)
const errorMessage = ref('')
const submitting = ref(false)
const confirming = ref(false)
const retrying = ref(false)
const downloading = ref(false)
let refreshTimer: number | undefined

const canSubmit = computed(() => Boolean(generator.JSESSIONID.trim() && generator.url.trim()))
const isActive = computed(() =>
  ['queued', 'running', 'cancel_requested'].includes(currentJob.value?.status || '')
)

onMounted(initialize)
onBeforeUnmount(stopRefresh)

async function initialize(): Promise<void> {
  if (typeof route.query.url === 'string') generator.url = route.query.url
  if (typeof route.query.dcc_job !== 'string') return
  await refreshJob(route.query.dcc_job)
}

async function previewDcc(): Promise<void> {
  if (!canSubmit.value) return
  submitting.value = true
  errorMessage.value = ''
  try {
    setCurrentJob(await previewDccDocumentJob(generator.JSESSIONID, generator.url))
    generator.JSESSIONID = ''
    window.$notification.success({
      title: 'DCC preview ready',
      description: 'Review the exact immutable snapshot before queueing it.'
    })
  } catch (error) {
    errorMessage.value = formatApiError(error)
  } finally {
    submitting.value = false
  }
}

async function confirmPreview(): Promise<void> {
  if (!currentJob.value || currentJob.value.status !== 'awaiting_confirmation') return
  confirming.value = true
  errorMessage.value = ''
  try {
    setCurrentJob(await confirmDccDocumentJob(currentJob.value.id))
    window.$notification.success({
      title: 'DCC queued',
      description: 'The reviewed snapshot is available to the worker.'
    })
  } catch (error) {
    errorMessage.value = formatApiError(error)
  } finally {
    confirming.value = false
  }
}

async function refreshJob(jobId = currentJob.value?.id): Promise<void> {
  if (!jobId) return
  try {
    setCurrentJob(await fetchJob(jobId), false)
  } catch (error) {
    errorMessage.value = formatApiError(error)
    stopRefresh()
  }
}

function setCurrentJob(job: Job, updateUrl = true): void {
  currentJob.value = job
  if (updateUrl) void router.replace({ query: { ...route.query, dcc_job: job.id } })
  scheduleRefresh()
}

function scheduleRefresh(): void {
  stopRefresh()
  if (isActive.value) refreshTimer = window.setTimeout(refreshJob, 2000)
}

function stopRefresh(): void {
  if (refreshTimer) window.clearTimeout(refreshTimer)
  refreshTimer = undefined
}

async function retryCurrentJob(): Promise<void> {
  if (!currentJob.value) return
  retrying.value = true
  try {
    setCurrentJob(await retryJob(currentJob.value.id))
  } catch (error) {
    errorMessage.value = formatApiError(error)
  } finally {
    retrying.value = false
  }
}

async function downloadCurrentJob(): Promise<void> {
  if (!currentJob.value) return
  downloading.value = true
  try {
    await downloadJob(currentJob.value)
  } catch (error) {
    errorMessage.value = formatApiError(error)
  } finally {
    downloading.value = false
  }
}

function openJobCenter(): void {
  if (currentJob.value) void router.push({ name: 'jobs', query: { job: currentJob.value.id } })
}
</script>
