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
import DccCreationPreview from '@/features/dcc/components/DccCreationPreview.vue'
import DccJobStatus from '@/features/dcc/components/DccJobStatus.vue'
import { formatApiError } from '@/shared/api/apiError'
import { confirmDccDocumentJob, previewDccDocumentJob } from '@/features/dcc/api/dccJobs'
import {
  cancelJob,
  downloadJob,
  fetchJob,
  isActiveJobStatus,
  type Job
} from '@/features/jobs/api/jobs'
import { useDccStore } from '@/features/dcc/stores/dcc'
const route = useRoute()
const router = useRouter()
const dccStore = useDccStore()
const generator = reactive({ url: '' })
const currentJob = ref<Job | null>(null)
const errorMessage = ref('')
const submitting = ref(false)
const confirming = ref(false)
const cancelling = ref(false)
const downloading = ref(false)
let refreshTimer: number | undefined
const canSubmit = computed(() => Boolean(dccStore.isJiraConnected && generator.url.trim()))
const isActive = computed(() => isActiveJobStatus(currentJob.value?.status))

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
    setCurrentJob(await previewDccDocumentJob(generator.url))
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
async function confirmPreview(warningCodes: string[]): Promise<void> {
  if (!currentJob.value || currentJob.value.status !== 'awaiting_confirmation') return
  confirming.value = true
  errorMessage.value = ''
  try {
    setCurrentJob(await confirmDccDocumentJob(currentJob.value.id, warningCodes))
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

async function cancelCurrentJob(): Promise<void> {
  if (!currentJob.value) return
  cancelling.value = true
  try {
    setCurrentJob(await cancelJob(currentJob.value.id))
    window.$message.success('Cancellation requested.')
  } catch (error) {
    errorMessage.value = formatApiError(error)
  } finally {
    cancelling.value = false
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
