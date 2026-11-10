<template>
  <n-flex justify="center">
    <n-card title="JIRA DCC Creator" class="app-page-container">
      <n-space vertical size="large">
        <n-alert type="info" :bordered="false">
          JIRA is read with the session connected from the JIRA workspace. The captured source and
          generated DOCX remain private in Job Center.
        </n-alert>
        <n-form label-placement="top" @submit.prevent="previewDcc">
          <n-form-item label="JIRA task URL or issue key">
            <n-input v-model:value="generator.url" placeholder="DCC-123 or JIRA browse URL" />
          </n-form-item>
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
          :cancelling="cancelling"
          :downloading="downloading"
          @cancel="cancelCurrentJob"
          @open="openJobCenter"
          @download="downloadCurrentJob"
        />
      </n-space>
    </n-card>
  </n-flex>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import DccCreationPreview from '@/features/integrations/jira/components/DccCreationPreview.vue'
import DccJobStatus from '@/features/integrations/jira/components/DccJobStatus.vue'
import { formatApiError } from '@/shared/api/apiError'
import {
  confirmDccDocumentJob,
  previewDccDocumentJob
} from '@/features/integrations/jira/api/dccJobs'
import {
  cancelJob,
  downloadJob,
  fetchJob,
  isActiveJobStatus,
  type Job
} from '@/features/jobs/api/jobs'
import { useJiraStore } from '@/features/integrations/jira/stores/jira'
const route = useRoute()
const router = useRouter()
const jiraStore = useJiraStore()
const generator = reactive({ url: '' })
const currentJob = ref<Job | null>(null)
const errorMessage = ref('')
const submitting = ref(false)
const confirming = ref(false)
const cancelling = ref(false)
const downloading = ref(false)
let refreshTimer: number | undefined
let disposed = false
let requestRevision = 0
const canSubmit = computed(() => Boolean(jiraStore.isJiraConnected && generator.url.trim()))
const isActive = computed(() => isActiveJobStatus(currentJob.value?.status))

onMounted(initialize)
onBeforeUnmount(() => {
  disposed = true
  requestRevision++
  stopRefresh()
})
async function initialize(): Promise<void> {
  if (typeof route.query.url === 'string') generator.url = route.query.url
  if (typeof route.query.dcc_job !== 'string') return
  await refreshJob(route.query.dcc_job)
}
async function previewDcc(): Promise<void> {
  if (disposed || !canSubmit.value) return
  const revision = beginJobRequest()
  submitting.value = true
  errorMessage.value = ''
  try {
    const job = await previewDccDocumentJob(generator.url)
    if (!isCurrentRequest(revision)) return
    setCurrentJob(job)
    window.$notification.success({
      title: 'DCC preview ready',
      description: 'Review the exact immutable snapshot before queueing it.',
      duration: 3000
    })
  } catch (error) {
    if (isCurrentRequest(revision)) errorMessage.value = formatApiError(error)
  } finally {
    if (isCurrentRequest(revision)) {
      submitting.value = false
      scheduleRefresh()
    }
  }
}
async function confirmPreview(warningCodes: string[]): Promise<void> {
  if (disposed || !currentJob.value || currentJob.value.status !== 'awaiting_confirmation') return
  const revision = beginJobRequest()
  confirming.value = true
  errorMessage.value = ''
  try {
    const job = await confirmDccDocumentJob(currentJob.value.id, warningCodes)
    if (!isCurrentRequest(revision)) return
    setCurrentJob(job)
    window.$notification.success({
      title: 'DCC queued',
      description: 'The reviewed snapshot is available to the worker.',
      duration: 3000
    })
  } catch (error) {
    if (isCurrentRequest(revision)) errorMessage.value = formatApiError(error)
  } finally {
    if (isCurrentRequest(revision)) {
      confirming.value = false
      scheduleRefresh()
    }
  }
}

async function refreshJob(jobId = currentJob.value?.id): Promise<void> {
  if (disposed || !jobId) return
  const revision = beginJobRequest()
  try {
    const job = await fetchJob(jobId)
    if (isCurrentRequest(revision)) setCurrentJob(job, false)
  } catch (error) {
    if (!isCurrentRequest(revision)) return
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
  if (!disposed && isActive.value) refreshTimer = window.setTimeout(refreshJob, 2000)
}

function beginJobRequest(): number {
  stopRefresh()
  submitting.value = false
  confirming.value = false
  cancelling.value = false
  return ++requestRevision
}

function isCurrentRequest(revision: number): boolean {
  return !disposed && revision === requestRevision
}

function stopRefresh(): void {
  if (refreshTimer !== undefined) window.clearTimeout(refreshTimer)
  refreshTimer = undefined
}

async function cancelCurrentJob(): Promise<void> {
  if (disposed || !currentJob.value) return
  const revision = beginJobRequest()
  cancelling.value = true
  try {
    const job = await cancelJob(currentJob.value.id)
    if (!isCurrentRequest(revision)) return
    setCurrentJob(job)
    window.$message.success('Cancellation requested.')
  } catch (error) {
    if (isCurrentRequest(revision)) errorMessage.value = formatApiError(error)
  } finally {
    if (isCurrentRequest(revision)) {
      cancelling.value = false
      scheduleRefresh()
    }
  }
}

async function downloadCurrentJob(): Promise<void> {
  if (disposed || !currentJob.value) return
  const jobId = currentJob.value.id
  downloading.value = true
  try {
    await downloadJob(currentJob.value)
  } catch (error) {
    if (!disposed && currentJob.value?.id === jobId) errorMessage.value = formatApiError(error)
  } finally {
    if (!disposed) downloading.value = false
  }
}

function openJobCenter(): void {
  if (currentJob.value) void router.push({ name: 'jobs', query: { job: currentJob.value.id } })
}
</script>
