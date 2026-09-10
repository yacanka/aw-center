import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useMessage } from 'naive-ui'
import type {
  CompDocDashboardSummary,
  DashboardPanel
} from '@/features/compliance/models/compdocDashboard'
import type { ProjectRegistryItem } from '@/features/projects/models/projectRegistry'
import { fetchCompdocDashboard } from '@/features/compliance/api/compdocDashboard'
import { formatApiError } from '@/shared/api/apiError'
import { useProjectCatalogStore } from '@/features/projects/stores/projectCatalog'

interface ProjectOption {
  label: string
  value: string
  disabled: boolean
}

/** Manage project options and race-safe loading for the CompDoc dashboard. */
export function useCompdocDashboard() {
  const message = useMessage()
  const projectCatalog = useProjectCatalogStore()
  const projectOptions = ref<ProjectOption[]>([])
  const activeProject = ref('')
  const summary = ref<CompDocDashboardSummary | null>(null)
  const loading = ref(false)
  const error = ref('')
  const selectedPanelId = ref<string | null>(null)
  const selectedPanel = computed(
    () => summary.value?.panels.find((panel) => panel.id === selectedPanelId.value) || null
  )
  const focusedAnalytics = computed(() => selectedPanel.value?.analytics || summary.value)
  let activeController: AbortController | null = null
  let requestSequence = 0
  let disposed = false

  async function loadProject(projectSlug: string) {
    const sequence = ++requestSequence
    activeController?.abort()
    const controller = new AbortController()
    activeController = controller
    if (projectSlug !== activeProject.value) {
      summary.value = null
      selectedPanelId.value = null
    }
    activeProject.value = projectSlug
    localStorage.setItem('allSummaryActiveTab', projectSlug)
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

  async function initialize() {
    await loadProjectOptions()
    if (disposed) return
    const initialProject = getInitialProjectSlug(projectOptions.value)
    if (initialProject) await loadProject(initialProject)
  }

  async function loadProjectOptions() {
    try {
      await projectCatalog.load()
      if (disposed) return
      projectOptions.value = projectCatalog.complianceProjects.map(createProjectOption)
    } catch (requestError) {
      if (disposed) return
      projectOptions.value = []
      message.warning(`Project list could not be refreshed: ${formatApiError(requestError)}`)
    }
  }

  onMounted(initialize)
  onBeforeUnmount(() => {
    disposed = true
    requestSequence += 1
    activeController?.abort()
  })

  return {
    activeProject,
    error,
    loading,
    loadProject,
    projectOptions,
    summary,
    focusedAnalytics,
    selectedPanel,
    togglePanel,
    clearPanel: () => (selectedPanelId.value = null)
  }
}

function createProjectOption(project: ProjectRegistryItem): ProjectOption {
  return { label: project.name, value: project.slug, disabled: false }
}

function getInitialProjectSlug(options: ProjectOption[]): string | null {
  const savedProject = localStorage.getItem('allSummaryActiveTab')
  const savedOption = options.find((option) => option.value === savedProject && !option.disabled)
  return savedOption?.value || options.find((option) => !option.disabled)?.value || null
}
