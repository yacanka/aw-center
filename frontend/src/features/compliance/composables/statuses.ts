import { onBeforeUnmount, ref, watch } from 'vue'
import { fetchCompdocStatuses, type CompdocStatus } from '../api/compdocStatuses'
import { formatApiError } from '@/shared/api/apiError'

/** Keep project vocabulary local to its mounted consumer, ignoring stale responses. */
export function useCompdocStatuses(project: () => string, enabled: () => boolean = () => true) {
  const statuses = ref<CompdocStatus[]>([])
  const loading = ref(false)
  const error = ref('')
  let requestId = 0
  async function load() {
    const request = ++requestId
    statuses.value = []
    error.value = ''
    loading.value = false
    if (!project() || !enabled()) return
    loading.value = true
    try {
      const result = await fetchCompdocStatuses(project())
      if (request === requestId) statuses.value = result
    } catch (failure) {
      if (request === requestId) error.value = formatApiError(failure)
    } finally {
      if (request === requestId) loading.value = false
    }
  }
  watch([project, enabled], load, { immediate: true })
  onBeforeUnmount(() => requestId++)
  return { statuses, loading, error, load }
}
