import { computed, onBeforeUnmount, ref, watch } from 'vue'
import type {
  CompDocDashboardSummary,
  DashboardPanel
} from '@/features/compliance/models/compdocDashboard'
import { fetchCompdocDashboard } from '@/features/compliance/api/compdocDashboard'
import { formatApiError } from '@/shared/api/apiError'
/** Load analytics for the authorized project selected by the route. */
export function useCompdocDashboard(project: () => string) {
  const activeProject = computed(project)
  const summary = ref<CompDocDashboardSummary | null>(null)
  const loading = ref(false)
  const error = ref('')
  const breakdownMode = ref<'panel' | 'ata'>('panel')
  const displayedPanels = computed(
    () =>
      (breakdownMode.value === 'panel' ? summary.value?.panel_groups : summary.value?.panels) || []
  )
  const selectedPanelId = ref<string | null>(null)
  const selectedPanel = computed(
    () => displayedPanels.value.find((panel) => panel.id === selectedPanelId.value) || null
  )
  watch(breakdownMode, () => (selectedPanelId.value = null))
  const focusedAnalytics = computed(() => selectedPanel.value?.analytics || summary.value)
  let activeController: AbortController | null = null
  let requestSequence = 0

  async function loadProject(projectSlug: string) {
    const sequence = ++requestSequence
    activeController?.abort()
    const controller = new AbortController()
    activeController = controller
    if (projectSlug !== summary.value?.project) {
      summary.value = null
      selectedPanelId.value = null
    }
    loading.value = true
    error.value = ''
    try {
      const result = await fetchCompdocDashboard(projectSlug, controller.signal)
      if (sequence === requestSequence) {
        summary.value = result
        if (!selectedPanel.value) selectedPanelId.value = null
      }
    } catch (requestError) {
      if (controller.signal.aborted || sequence !== requestSequence) return
      summary.value = null
      error.value = formatApiError(requestError)
    } finally {
      if (sequence === requestSequence) loading.value = false
    }
  }

  function togglePanel(panel: DashboardPanel) {
    selectedPanelId.value = selectedPanelId.value === panel.id ? null : panel.id
  }

  watch(activeProject, loadProject, { immediate: true })
  onBeforeUnmount(() => {
    requestSequence += 1
    activeController?.abort()
  })

  return {
    activeProject,
    breakdownMode,
    displayedPanels,
    error,
    loading,
    loadProject,
    summary,
    focusedAnalytics,
    selectedPanel,
    togglePanel,
    clearPanel: () => (selectedPanelId.value = null)
  }
}
