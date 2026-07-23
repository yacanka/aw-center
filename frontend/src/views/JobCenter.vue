<template>
  <n-space vertical size="large">
    <n-card>
      <n-space justify="space-between" align="center">
        <div>
          <n-h2 style="margin: 0">Job Center</n-h2>
          <n-text depth="3">Durable operations, progress, retries, and output artifacts.</n-text>
        </div>
        <n-space align="center">
          <n-switch v-model:value="autoRefresh">Auto refresh</n-switch>
          <n-button :loading="loading" @click="loadJobs">Refresh</n-button>
        </n-space>
      </n-space>
    </n-card>

    <n-alert v-if="errorMessage" type="error" closable @close="errorMessage = ''">
      {{ errorMessage }}
    </n-alert>
    <n-alert v-if="systemStatus && !systemStatus.available" type="warning" :bordered="false">
      No background worker is currently reporting. Queued jobs are safe and will start when a worker
      becomes available.
    </n-alert>
    <n-alert v-else-if="systemStatus" type="success" :bordered="false">
      {{ systemStatus.active_workers }} worker{{ systemStatus.active_workers === 1 ? '' : 's' }}
      available.
    </n-alert>
    <n-empty v-if="!loading && jobs.length === 0" description="No jobs have been queued yet." />

    <n-list v-else bordered>
      <JobListItem
        v-for="job in jobs"
        :key="job.id"
        :job="job"
        :active="activeJobId === job.id"
        @details="showDetails"
        @cancel="cancel"
        @retry="retry"
        @download="download"
      />
    </n-list>
    <n-pagination
      v-if="totalJobs > pageSize"
      v-model:page="currentPage"
      :page-size="pageSize"
      :item-count="totalJobs"
      @update:page="loadJobs"
    />
    <JobDetailDrawer
      v-model:show="detailsVisible"
      :job="selectedJob"
      :loading="detailsLoading"
      :handoff-loading="activeJobId === selectedJob?.id"
      @handoff="handoff"
      @open-job="showJobDetails"
    />
  </n-space>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import JobListItem from '@/components/jobs/JobListItem.vue'
import JobDetailDrawer from '@/components/jobs/JobDetailDrawer.vue'
import { formatApiError } from '@/services/apiError'
import {
  cancelJob,
  createJobHandoff,
  downloadJob,
  fetchJob,
  fetchJobSystemStatus,
  fetchJobs,
  retryJob,
  type Job,
  type JobHandoff,
  type JobSystemStatus
} from '@/services/jobs'

const jobs = ref<Job[]>([])
const route = useRoute()
const loading = ref(false)
const autoRefresh = ref(true)
const errorMessage = ref('')
const activeJobId = ref('')
const systemStatus = ref<JobSystemStatus | null>(null)
const currentPage = ref(1)
const pageSize = 20
const totalJobs = ref(0)
const selectedJob = ref<Job | null>(null)
const detailsVisible = ref(false)
const detailsLoading = ref(false)
let refreshTimer: number | undefined

onMounted(initializeJobs)
onBeforeUnmount(stopRefreshTimer)
watch(autoRefresh, scheduleRefresh)

async function initializeJobs(): Promise<void> {
  await loadJobs()
  const linkedJobId = route.query.job
  if (typeof linkedJobId === 'string') await showJobDetails(linkedJobId)
}

async function loadJobs(): Promise<void> {
  loading.value = true
  stopRefreshTimer()
  try {
    const [jobPage, currentSystemStatus] = await Promise.all([
      fetchJobs(currentPage.value, pageSize),
      fetchJobSystemStatus()
    ])
    jobs.value = jobPage.results
    totalJobs.value = jobPage.count
    systemStatus.value = currentSystemStatus
    errorMessage.value = ''
  } catch (error) {
    errorMessage.value = formatApiError(error)
  } finally {
    loading.value = false
    scheduleRefresh()
  }
}

async function cancel(job: Job): Promise<void> {
  await runAction(job, () => cancelJob(job.id), 'Cancellation requested.')
}

async function retry(job: Job): Promise<void> {
  await runAction(job, () => retryJob(job.id), 'Retry queued.')
}

async function handoff(job: Job, option: JobHandoff): Promise<void> {
  activeJobId.value = job.id
  try {
    const targetJob = await createJobHandoff(job.id, option.id)
    window.$message.success(`${option.label} is ready in Job Center.`)
    await loadJobs()
    await showJobDetails(targetJob.id)
  } catch (error) {
    window.$message.error(formatApiError(error))
  } finally {
    activeJobId.value = ''
  }
}

async function download(job: Job): Promise<void> {
  try {
    await downloadJob(job)
  } catch (error) {
    window.$message.error(formatApiError(error))
  }
}

async function showDetails(job: Job): Promise<void> {
  await showJobDetails(job.id)
}

async function showJobDetails(jobId: string): Promise<void> {
  detailsVisible.value = true
  detailsLoading.value = true
  try {
    selectedJob.value = await fetchJob(jobId)
  } catch (error) {
    window.$message.error(formatApiError(error))
  } finally {
    detailsLoading.value = false
  }
}

async function runAction(
  job: Job,
  action: () => Promise<Job>,
  successMessage: string
): Promise<void> {
  activeJobId.value = job.id
  try {
    await action()
    window.$message.success(successMessage)
    await loadJobs()
  } catch (error) {
    window.$message.error(formatApiError(error))
  } finally {
    activeJobId.value = ''
  }
}

function scheduleRefresh(): void {
  stopRefreshTimer()
  if (autoRefresh.value) refreshTimer = window.setTimeout(loadJobs, 3000)
}

function stopRefreshTimer(): void {
  if (refreshTimer) window.clearTimeout(refreshTimer)
  refreshTimer = undefined
}
</script>
