import { computed, reactive } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import type { DccCompdocSelection } from '@/services/dccJobs'

/** Manage the bounded CompDoc route context used by DCC Creator. */
export function useDccCompdocSelection() {
  const route = useRoute()
  const router = useRouter()
  const selection = reactive<DccCompdocSelection>({ project: '', documentIds: [] })
  const hasSelection = computed(() => Boolean(selection.project && selection.documentIds.length))

  function initialize(): void {
    if (typeof route.query.compdoc_project !== 'string') return
    if (typeof route.query.compdocs !== 'string') return
    const documentIds = route.query.compdocs.split(',').filter(Boolean)
    if (!documentIds.length) return
    selection.project = route.query.compdoc_project
    selection.documentIds = documentIds
  }

  function clear(): void {
    selection.project = ''
    selection.documentIds = []
    const query = { ...route.query }
    delete query.compdoc_project
    delete query.compdocs
    void router.replace({ query })
  }

  return { selection, hasSelection, initialize, clear }
}
