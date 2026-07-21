import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useMessage } from 'naive-ui'
import type { CompDocDashboardSummary } from '@/models/compdocDashboard'
import type { ProjectRegistryItem } from '@/models/projectRegistry'
import { fetchCompdocDashboard } from '@/services/compdocDashboard'
import { formatApiError } from '@/services/apiError'
import { PROJECT_REGISTRY_FALLBACK, fetchCompdocProjectRegistry } from '@/services/projectRegistry'

interface ProjectOption {
  label: string
  value: string
  disabled: boolean
}

/** Manage project options and race-safe loading for the CompDoc dashboard. */
export function useCompdocDashboard() {
  const message = useMessage()
  const projectOptions = ref(PROJECT_REGISTRY_FALLBACK.map(createProjectOption))
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
    await loadProject(getInitialProjectSlug(projectOptions.value))
  }

  async function loadProjectOptions() {
    try {
      projectOptions.value = (await fetchCompdocProjectRegistry()).map(createProjectOption)
    } catch (requestError) {
      message.warning(`Project list could not be refreshed: ${formatApiError(requestError)}`)
    }
  }

  onMounted(initialize)
  onBeforeUnmount(() => activeController?.abort())

  return {
    activeProject,
    dataQualityIssues: computed(() => summary.value?.data_quality.issue_count || 0),
    error,
    loading,
    loadProject,
    projectOptions,
    summary
  }
}

function createProjectOption(project: ProjectRegistryItem): ProjectOption {
  return { label: project.display_name, value: project.slug, disabled: !project.enabled }
}

function getInitialProjectSlug(options: ProjectOption[]): string {
  const savedProject = localStorage.getItem('allSummaryActiveTab')
  const savedOption = options.find((option) => option.value === savedProject && !option.disabled)
  return savedOption?.value || options.find((option) => !option.disabled)?.value || 'ozgur'
}
