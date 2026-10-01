import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter, type RouteLocationNormalizedLoaded, type Router } from 'vue-router'
import { formatApiError } from '@/shared/api/apiError'
import {
  cancelJob,
  downloadJob,
  fetchJob,
  isActiveJobStatus,
  type Job
} from '@/features/jobs/api/jobs'

const REFRESH_INTERVAL_MILLISECONDS = 2000

class PageJobMonitor {
  readonly job = ref<Job | null>(null)
  readonly errorMessage = ref('')
  readonly cancelling = ref(false)
  readonly downloading = ref(false)
  readonly active = computed(() => isActiveJobStatus(this.job.value?.status))
  private refreshTimer: number | undefined
  private revision = 0
  private disposed = false

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
    const revision = this.revision
    try {
      const next = await fetchJob(jobId)
      if (this.disposed || revision !== this.revision) return
      this.setJob(next, false)
      this.errorMessage.value = ''
    } catch (error) {
      if (this.disposed || revision !== this.revision) return
      this.errorMessage.value = formatApiError(error)
      this.stopRefresh()
    }
  }

  readonly setJob = (nextJob: Job, updateUrl = true): void => {
    if (this.disposed) return
    if (updateUrl) this.revision++
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

  /** Detach the old input and invalidate any outstanding restoration/poll. */
  readonly reset = (): void => {
    this.revision++
    this.stopRefresh()
    this.job.value = null
    this.errorMessage.value = ''
    const query = { ...this.route.query }
    delete query[this.queryKey]
    void this.router.replace({ query })
  }

  readonly dispose = (): void => {
    this.disposed = true
    this.revision++
    this.stopRefresh()
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
      refresh: () => (this.job.value ? this.refresh() : this.restore()),
      reset: this.reset,
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
  onBeforeUnmount(monitor.dispose)
  return monitor.bindings
}
