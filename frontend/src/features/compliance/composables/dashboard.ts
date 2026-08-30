import { onBeforeUnmount, onMounted, ref } from 'vue'
import { useMessage } from 'naive-ui'
import type { CompDocDashboardSummary } from '@/features/compliance/models/compdocDashboard'
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
  let activeController: AbortController | null = null
  let requestSequence = 0

  async function loadProject(projectSlug: string) {
    const sequence = ++requestSequence
    activeController?.abort()
    activeController = new AbortController()
    activeProject.value = projectSlug
    localStorage.setItem('allSummaryActiveTab', projectSlug)
    loading.value = true
    error.value = ''
    try {
      const result = await fetchCompdocDashboard(projectSlug, activeController.signal)
      if (sequence === requestSequence) summary.value = result
    } catch (requestError) {
      if (activeController.signal.aborted || sequence !== requestSequence) return
      summary.value = null
      error.value = formatApiError(requestError)
    } finally {
      if (sequence === requestSequence) loading.value = false
    }
  }

  async function initialize() {
    await loadProjectOptions()
    const initialProject = getInitialProjectSlug(projectOptions.value)
    if (initialProject) await loadProject(initialProject)
  }

  async function loadProjectOptions() {
    try {
      projectOptions.value = (await projectCatalog.load()).map(createProjectOption)
    } catch (requestError) {
      projectOptions.value = []
      message.warning(`Project list could not be refreshed: ${formatApiError(requestError)}`)
    }
  }

  onMounted(initialize)
  onBeforeUnmount(() => activeController?.abort())

  return {
    activeProject,
    error,
    loading,
    loadProject,
    projectOptions,
    summary
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
