<template>
  <n-space vertical size="small" class="job-overview">
    <n-alert
      v-if="errorMessage"
      type="error"
      title="Work overview could not be loaded"
      :bordered="false"
    >
      {{ errorMessage }}
    </n-alert>
    <n-grid cols="1 l:2" responsive="screen" :x-gap="16" :y-gap="16">
      <n-grid-item>
        <n-card title="My work" size="small" class="home-card">
          <template #header-extra>
            <n-button quaternary size="small" :loading="loading" @click="loadJobs"
              >Refresh</n-button
            >
          </template>
          <n-skeleton v-if="loading && !systemStatus" text :repeat="3" />
          <template v-else>
            <n-grid cols="3" :x-gap="8">
              <n-grid-item v-for="metric in metrics" :key="metric.status">
                <div class="metric">
                  <strong>{{ metric.value }}</strong>
                  <n-text depth="3">{{ metric.label }}</n-text>
                </div>
              </n-grid-item>
            </n-grid>
            <n-alert
              v-if="hasPendingWork && systemStatus && !systemStatus.available"
              type="warning"
              :bordered="false"
              class="worker-status"
            >
              Work is safely queued; no worker is currently reporting.
            </n-alert>
            <n-button secondary type="primary" class="card-action" @click="openJobCenter">
              Open Job Center
            </n-button>
          </template>
        </n-card>
      </n-grid-item>
      <n-grid-item>
        <n-card title="Recent activity" size="small" class="home-card">
          <template #header-extra><n-text depth="3">Successful outputs</n-text></template>
          <n-skeleton v-if="loading && !jobs.length" text :repeat="3" />
          <n-empty v-else-if="!recentJobs.length" description="No recent completed work." />
          <n-list v-else>
            <n-list-item v-for="job in recentJobs" :key="job.id">
              <n-thing :title="job.title" :description="completedLabel(job)">
                <template #action>
                  <n-space>
                    <n-button size="tiny" quaternary @click="openJob(job)">Details</n-button>
                    <n-button
                      v-if="job.download_url"
                      size="tiny"
                      type="primary"
                      :loading="downloadingJobId === job.id"
                      @click="download(job)"
                    >
                      Download
                    </n-button>
                  </n-space>
                </template>
              </n-thing>
            </n-list-item>
          </n-list>
        </n-card>
      </n-grid-item>
    </n-grid>
  </n-space>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { formatApiError } from '@/services/apiError'
import { buildWorkMetrics, recentSuccessfulJobs } from '@/services/homeDashboard'
import {
  downloadJob,
  fetchJobs,
  fetchJobSystemStatus,
  type Job,
  type JobSystemStatus
} from '@/services/jobs'

const router = useRouter()
const jobs = ref<Job[]>([])
const systemStatus = ref<JobSystemStatus | null>(null)
const loading = ref(false)
const errorMessage = ref('')
const downloadingJobId = ref('')
const metrics = computed(() => buildWorkMetrics(systemStatus.value))
const hasPendingWork = computed(() => metrics.value.some((metric) => metric.value > 0))
const recentJobs = computed(() => recentSuccessfulJobs(jobs.value))

onMounted(loadJobs)

async function loadJobs(): Promise<void> {
  loading.value = true
  try {
    const [jobPage, status] = await Promise.all([fetchJobs(1, 20), fetchJobSystemStatus()])
    jobs.value = jobPage.results
    systemStatus.value = status
    errorMessage.value = ''
  } catch (error) {
    errorMessage.value = formatApiError(error)
  } finally {
    loading.value = false
  }
}

async function download(job: Job): Promise<void> {
  downloadingJobId.value = job.id
  try {
    await downloadJob(job)
  } catch (error) {
    window.$message.error(formatApiError(error))
  } finally {
    downloadingJobId.value = ''
  }
}

function openJobCenter(): void {
  void router.push('/jobs')
}

function openJob(job: Job): void {
  void router.push({ path: '/jobs', query: { job: job.id } })
}

function completedLabel(job: Job): string {
  const date = job.completed_at || job.updated_at
  return `${job.output_name || 'Workflow completed'} · ${new Intl.DateTimeFormat(undefined, {
    dateStyle: 'short',
    timeStyle: 'short'
  }).format(new Date(date))}`
}
</script>

<style scoped>
.job-overview {
  margin-bottom: 16px;
}

.home-card {
  height: 100%;
}

.metric {
  align-items: center;
  background: rgba(24, 160, 88, 0.08);
  border-radius: 8px;
  display: grid;
  min-height: 74px;
  padding: 10px;
  text-align: center;
}

.metric strong {
  font-size: 24px;
}

.worker-status,
.card-action {
  margin-top: 12px;
}
</style>
