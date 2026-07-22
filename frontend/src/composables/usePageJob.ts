import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter, type RouteLocationNormalizedLoaded, type Router } from 'vue-router'
import { formatApiError } from '@/services/apiError'
import { cancelJob, downloadJob, fetchJob, retryJob, type Job } from '@/services/jobs'

const ACTIVE_STATUSES = new Set(['queued', 'running', 'cancel_requested'])
const REFRESH_INTERVAL_MILLISECONDS = 2000

class PageJobMonitor {
  readonly job = ref<Job | null>(null)
  readonly errorMessage = ref('')
  readonly cancelling = ref(false)
  readonly retrying = ref(false)
  readonly downloading = ref(false)
  readonly active = computed(() => ACTIVE_STATUSES.has(this.job.value?.status || ''))
  private refreshTimer: number | undefined

  constructor(
    private readonly queryKey: string,
    private readonly route: RouteLocationNormalizedLoaded,
    private readonly router: Router
  ) {}

  readonly restore = async (): Promise<void> => {
    const jobId = this.route.query[this.queryKey]
    if (typeof jobId === 'string') await this.refresh(jobId)
  }

  readonly refresh = async (jobId = this.job.value?.id): Promise<void> => {
    if (!jobId) return
    try {
      this.setJob(await fetchJob(jobId), false)
      this.errorMessage.value = ''
    } catch (error) {
      this.errorMessage.value = formatApiError(error)
      this.stopRefresh()
    }
  }

  readonly setJob = (nextJob: Job, updateUrl = true): void => {
    this.job.value = nextJob
    if (updateUrl) {
      void this.router.replace({
        query: { ...this.route.query, [this.queryKey]: nextJob.id }
      })
    }
    this.scheduleRefresh()
  }

  readonly cancel = async (): Promise<void> => {
    const currentJob = this.job.value
    if (!currentJob) return
    this.cancelling.value = true
    await this.runAction(() => cancelJob(currentJob.id), 'Cancellation requested.')
    this.cancelling.value = false
  }

  readonly retry = async (): Promise<void> => {
    const currentJob = this.job.value
    if (!currentJob) return
    this.retrying.value = true
    await this.runAction(() => retryJob(currentJob.id), 'Retry queued.')
    this.retrying.value = false
  }

  readonly download = async (): Promise<void> => {
    const currentJob = this.job.value
    if (!currentJob) return
    this.downloading.value = true
    try {
      await downloadJob(currentJob)
    } catch (error) {
      this.errorMessage.value = formatApiError(error)
    } finally {
      this.downloading.value = false
    }
  }

  readonly openJobCenter = (): void => {
    if (this.job.value) {
      void this.router.push({ name: 'jobs', query: { job: this.job.value.id } })
    }
  }

  readonly stopRefresh = (): void => {
    if (this.refreshTimer) window.clearTimeout(this.refreshTimer)
    this.refreshTimer = undefined
  }

  get bindings() {
    return {
      active: this.active,
      cancel: this.cancel,
      cancelling: this.cancelling,
      download: this.download,
      downloading: this.downloading,
      errorMessage: this.errorMessage,
      job: this.job,
      openJobCenter: this.openJobCenter,
      retry: this.retry,
      retrying: this.retrying,
      setJob: this.setJob
    }
  }

  private scheduleRefresh(): void {
    this.stopRefresh()
    if (this.active.value) {
      this.refreshTimer = window.setTimeout(this.refresh, REFRESH_INTERVAL_MILLISECONDS)
    }
  }

  private async runAction(action: () => Promise<Job>, message: string): Promise<void> {
    this.errorMessage.value = ''
    try {
      this.setJob(await action())
      window.$message.success(message)
    } catch (error) {
      this.errorMessage.value = formatApiError(error)
    }
  }
}

/** Keep one page-owned durable job current and expose its safe actions. */
export function usePageJob(queryKey: string) {
  const monitor = new PageJobMonitor(queryKey, useRoute(), useRouter())
  onMounted(monitor.restore)
  onBeforeUnmount(monitor.stopRefresh)
  return monitor.bindings
}
