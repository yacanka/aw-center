import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { cancelJob, downloadJob, type Job } from '@/features/jobs/api/jobs'
import { usePageJob } from '@/features/jobs/composables/usePageJob'
import {
  enqueueDoorsModuleAttributes,
  fetchDoorsModuleAttributesResult
} from '@/features/integrations/api/doorsAutomation'
import { formatApiError } from '@/shared/api/apiError'

const QUERY_KEY = 'doors_scripter_attributes_job'

/** Optional attribute discovery; manual mappings remain usable after any failed load. */
export function useDoorsScriptAttributes() {
  const monitor = usePageJob(QUERY_KEY)
  const modulePath = ref('')
  const names = ref<string[]>([])
  const error = ref('')
  const enqueuing = ref(false)
  const readingResult = ref(false)
  const restoring = ref(typeof useRoute().query[QUERY_KEY] === 'string')
  const loaded = computed(() => names.value.length > 0)
  const loading = computed(
    () => enqueuing.value || monitor.active.value || readingResult.value || restoring.value
  )
  const options = computed(() => names.value.map((name) => ({ label: name, value: name })))
  let revision = 0
  let disposed = false
  let attempt: { path: string; key: string } | undefined
  let requestedPath: string | undefined

  onBeforeUnmount(() => {
    disposed = true
    revision++
  })
  watch(monitor.errorMessage, (message) => {
    if (!message) return
    // A stopped poll must not lock the optional discovery flow indefinitely.
    revision++
    error.value = message
    restoring.value = false
    readingResult.value = false
    monitor.reset()
  })
  watch(
    () => [monitor.job.value?.id, monitor.job.value?.status],
    () => {
      if (monitor.job.value) restoring.value = false
      if (monitor.job.value?.status === 'succeeded') void readResult(monitor.job.value)
    }
  )

  async function readResult(job: Job) {
    const currentRevision = revision
    readingResult.value = true
    try {
      const result = await fetchDoorsModuleAttributesResult(job)
      if (disposed || currentRevision !== revision || monitor.job.value?.id !== job.id) return
      if (requestedPath && result.module_path !== requestedPath)
        throw new Error('The attribute result belongs to a different module.')
      if (!result.attributes.length)
        throw new Error('No object attributes were found. Manual mapping remains available.')
      modulePath.value = result.module_path
      names.value = result.attributes
      error.value = ''
    } catch (failure) {
      if (!disposed && currentRevision === revision) error.value = formatApiError(failure)
    } finally {
      if (!disposed && currentRevision === revision) readingResult.value = false
    }
  }

  async function load() {
    if (loading.value || loaded.value) return
    const path = modulePath.value.trim()
    if (!path) {
      error.value = 'Enter a DOORS module path.'
      return
    }
    revision++
    const currentRevision = revision
    requestedPath = path
    monitor.reset()
    monitor.cancelling.value = false
    monitor.downloading.value = false
    error.value = ''
    enqueuing.value = true
    if (attempt?.path !== path) attempt = { path, key: crypto.randomUUID() }
    try {
      const job = await enqueueDoorsModuleAttributes(path, attempt.key)
      if (disposed || currentRevision !== revision) return
      attempt = undefined
      monitor.setJob(job)
    } catch (failure) {
      if (!disposed && currentRevision === revision) error.value = formatApiError(failure)
    } finally {
      if (!disposed && currentRevision === revision) enqueuing.value = false
    }
  }

  function unload() {
    revision++
    names.value = []
    error.value = ''
    requestedPath = undefined
    enqueuing.value = false
    readingResult.value = false
    restoring.value = false
    monitor.reset()
    monitor.cancelling.value = false
    monitor.downloading.value = false
  }

  function isCurrent(requestRevision: number, jobId: string) {
    return !disposed && requestRevision === revision && monitor.job.value?.id === jobId
  }

  // Contain action results here: a previous load must not mutate the new monitor.
  async function cancelAttributes() {
    const job = monitor.job.value
    if (!job || monitor.cancelling.value) return
    const requestRevision = revision
    monitor.cancelling.value = true
    error.value = ''
    try {
      const next = await cancelJob(job.id)
      if (!isCurrent(requestRevision, job.id)) return
      monitor.setJob(next)
      window.$message.success('Cancellation requested.')
    } catch (failure) {
      if (isCurrent(requestRevision, job.id)) error.value = formatApiError(failure)
    } finally {
      if (isCurrent(requestRevision, job.id)) monitor.cancelling.value = false
    }
  }

  async function downloadAttributes() {
    const job = monitor.job.value
    if (!job || monitor.downloading.value) return
    const requestRevision = revision
    monitor.downloading.value = true
    error.value = ''
    try {
      await downloadJob(job)
    } catch (failure) {
      if (isCurrent(requestRevision, job.id)) error.value = formatApiError(failure)
    } finally {
      if (isCurrent(requestRevision, job.id)) monitor.downloading.value = false
    }
  }

  return {
    modulePath,
    names,
    options,
    loaded,
    loading,
    load,
    unload,
    monitor: { ...monitor, cancel: cancelAttributes, download: downloadAttributes },
    error: computed(() => error.value || monitor.errorMessage.value)
  }
}
