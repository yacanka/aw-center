import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue'
import type { JiraFieldValue } from '@/features/integrations/jira/models/jira'
import { formatApiError } from '@/shared/api/apiError'
import type { Job } from '@/features/jobs/api/jobs'
import {
  approveJiraIssueDraft,
  createJiraIssueDraft,
  fetchJiraIssueDraft,
  preflightJiraIssueDraft,
  publishJiraIssueDraft,
  updateJiraIssueDraft,
  type JiraIssueDraft,
  type JiraIssueDraftPreflight
} from '@/features/integrations/jira/api/jiraIssueDrafts'
import { useJiraStore } from '@/features/integrations/jira/stores/jira'
import { useProjectCatalogStore } from '@/features/projects/stores/projectCatalog'
import { hasProjectJiraRole } from '@/features/projects/models/projectRegistry'

/** Coordinate the owner-visible JIRA draft review lifecycle for one selected job. */
export function useJiraIssueDraft(selectedJob: () => Job) {
  const jiraStore = useJiraStore()
  const projectCatalog = useProjectCatalogStore()
  const draft = ref<JiraIssueDraft | null>(null)
  const busy = ref(false)
  const preflight = ref<JiraIssueDraftPreflight | null>(null)
  const publicationJob = ref<Job | null>(null)
  const projectOptions = ref<Array<{ label: string; value: string }>>([])
  const selectedProjectSlugs = ref<string[]>([])
  const projectsLoading = ref(false)
  let selectionRevision = 0
  const editingVersion = ref(0)
  let disposed = false
  let publicationAttempt: { fingerprint: string; key: string } | null = null
  const form = reactive({
    project_key: '',
    summary: '',
    description: '',
    extra_fields: {} as Record<string, JiraFieldValue>
  })
  const eligible = computed(() => {
    const job = selectedJob()
    return job.kind === 'word.analyze' && job.status === 'succeeded'
  })
  const locked = computed(() => ['publishing', 'published'].includes(draft.value?.status || ''))
  const publishable = computed(() =>
    ['approved', 'failed', 'reconciliation_required'].includes(draft.value?.status || '')
  )
  const requiresReconciliation = computed(() => draft.value?.status === 'reconciliation_required')
  const canEdit = computed(() => Boolean(draft.value?.allowed_actions.edit))
  const canApprove = computed(() => Boolean(draft.value?.allowed_actions.approve))
  const canPreflight = computed(() => Boolean(draft.value?.allowed_actions.preflight))
  const canPublish = computed(() => Boolean(draft.value?.allowed_actions.publish))
  const canPrepare = computed(
    () =>
      eligible.value &&
      !draft.value &&
      !busy.value &&
      selectedProjectSlugs.value.length > 0 &&
      selectedProjectSlugs.value.every((slug) =>
        projectOptions.value.some((option) => option.value === slug)
      )
  )
  const isJiraConnected = computed(() => jiraStore.isJiraConnected)
  const statusType = computed(() => draftStatusType(draft.value))
  const dirty = computed(
    () => draft.value != null && draftFingerprint(draft.value) != formFingerprint(form)
  )
  const hasSaveConflict = computed(
    () => dirty.value && draft.value?.version !== editingVersion.value
  )

  watch(() => selectedJob().id, loadExistingDraft, { immediate: true, flush: 'sync' })
  onBeforeUnmount(() => {
    disposed = true
    selectionRevision++
  })
  void jiraStore.fetchJiraConnection().catch(() => undefined)

  function captureSelection(): () => boolean {
    const revision = selectionRevision
    const jobId = selectedJob().id
    return () => !disposed && revision === selectionRevision && jobId === selectedJob().id
  }

  function canActOnDraft(): boolean {
    return (
      !disposed && !busy.value && eligible.value && draft.value?.source_job === selectedJob().id
    )
  }

  async function loadExistingDraft(): Promise<void> {
    selectionRevision++
    const isCurrent = captureSelection()
    resetPanel()
    if (!eligible.value) return
    const reference = selectedJob().jira_draft
    busy.value = true
    try {
      if (!reference) await loadProjectOptions(isCurrent)
      else {
        const loaded = await fetchJiraIssueDraft(reference.id)
        if (isCurrent()) setDraft(loaded)
      }
    } catch (error) {
      if (isCurrent()) window.$message.error(formatApiError(error))
    } finally {
      if (isCurrent()) busy.value = false
    }
  }

  async function prepareDraft(): Promise<void> {
    const jobId = selectedJob().id
    if (!canPrepare.value) return
    await run(
      () => createJiraIssueDraft(jobId, [...selectedProjectSlugs.value]),
      setDraft,
      'JIRA draft is ready.'
    )
  }

  async function saveDraft(): Promise<void> {
    const current = draft.value
    if (
      !current ||
      !canActOnDraft() ||
      !canEdit.value ||
      locked.value ||
      !dirty.value ||
      hasSaveConflict.value
    )
      return
    const values = { ...form, version: editingVersion.value }
    await run(() => updateJiraIssueDraft(current.id, values), setDraft, 'Draft saved.')
  }

  function keepEditsAfterConflict(): void {
    if (!hasSaveConflict.value || !canActOnDraft() || !canEdit.value || locked.value) return
    editingVersion.value = draft.value!.version
  }

  function reloadSavedDraft(): void {
    if (!hasSaveConflict.value || !canActOnDraft()) return
    setDraft(draft.value!)
  }

  async function approveDraft(): Promise<void> {
    const current = draft.value
    if (
      !current ||
      !canActOnDraft() ||
      !canApprove.value ||
      dirty.value ||
      current.status !== 'draft'
    )
      return
    await run(
      () => approveJiraIssueDraft(current),
      (value) => setDraft(value, true),
      'Version approved.'
    )
  }

  async function checkPreflight(): Promise<void> {
    const current = draft.value
    if (!current || !canActOnDraft() || !canPreflight.value || dirty.value || locked.value) return
    await run(
      () => preflightJiraIssueDraft(current),
      (value) => {
        preflight.value = value
      },
      'JIRA requirements checked.'
    )
  }

  function setExtraField(identifier: string, value: JiraFieldValue): void {
    if (!canActOnDraft() || !canEdit.value || locked.value) return
    form.extra_fields[identifier] = value
  }

  async function publishDraft(): Promise<void> {
    const current = draft.value
    if (
      !current ||
      !canActOnDraft() ||
      !canPublish.value ||
      !publishable.value ||
      dirty.value ||
      !isJiraConnected.value ||
      (!requiresReconciliation.value && !preflight.value?.ready)
    )
      return
    await run(
      async (isCurrent) => {
        const fingerprint = `${current.id}:${current.version}:${current.status}`
        if (publicationAttempt?.fingerprint !== fingerprint) {
          publicationAttempt = { fingerprint, key: crypto.randomUUID() }
        }
        const job = await publishJiraIssueDraft(current, publicationAttempt.key)
        if (!isCurrent()) return { job, draft: current }
        try {
          return { job, draft: await fetchJiraIssueDraft(current.id) }
        } catch {
          return {
            job,
            draft: {
              ...current,
              status: 'publishing',
              version: current.version + 1,
              publication_job: job.id
            } as JiraIssueDraft
          }
        }
      },
      (result) => {
        publicationJob.value = result.job
        setDraft(result.draft, true)
      },
      requiresReconciliation.value
        ? 'JIRA reconciliation job queued.'
        : 'JIRA publication job queued.'
    )
  }

  async function run<T>(
    action: (isCurrent: () => boolean) => Promise<T>,
    accept: (value: T) => void,
    successMessage: string
  ): Promise<void> {
    if (disposed || busy.value) return
    const isCurrent = captureSelection()
    busy.value = true
    try {
      const value = await action(isCurrent)
      if (!isCurrent()) return
      accept(value)
      window.$message.success(successMessage)
    } catch (error) {
      if (!isCurrent()) return
      await recoverDraft(isCurrent)
      if (isCurrent()) window.$message.error(formatApiError(error))
    } finally {
      if (isCurrent()) busy.value = false
    }
  }

  async function recoverDraft(isCurrent: () => boolean): Promise<void> {
    const current = draft.value
    if (!current) return
    // Keep field editors available for corrections without reusing publication readiness.
    const previousPreflight = preflight.value
    preflight.value =
      previousPreflight && previousPreflight.project_key === form.project_key
        ? {
            ...previousPreflight,
            ready: false,
            missing_fields: [],
            invalid_fields: [],
            unsupported_fields: [],
            warnings: []
          }
        : null
    try {
      const recovered = await fetchJiraIssueDraft(current.id)
      if (!isCurrent()) return
      if (!dirty.value || formFingerprint(form) === draftFingerprint(recovered)) {
        setDraft(recovered)
        return
      }
      // Keep the editing CAS version until the user compares and resolves the conflict.
      draft.value = recovered
      selectedProjectSlugs.value = [...recovered.project_slugs]
    } catch {
      // Keep the last known version and form during an outage; retries still use server CAS.
    }
  }

  function setDraft(value: JiraIssueDraft, preservePreflight = false): void {
    draft.value = value
    editingVersion.value = value.version
    form.project_key = value.project_key
    form.summary = value.summary
    form.description = value.description
    form.extra_fields = { ...value.extra_fields }
    selectedProjectSlugs.value = [...value.project_slugs]
    if (!preservePreflight) preflight.value = null
  }

  function resetPanel(): void {
    busy.value = false
    projectsLoading.value = false
    draft.value = null
    editingVersion.value = 0
    preflight.value = null
    publicationJob.value = null
    publicationAttempt = null
    selectedProjectSlugs.value = []
    projectOptions.value = []
    form.project_key = ''
    form.summary = ''
    form.description = ''
    form.extra_fields = {}
  }

  async function loadProjectOptions(isCurrent: () => boolean): Promise<void> {
    projectsLoading.value = true
    try {
      await projectCatalog.load()
      if (!isCurrent()) return
      projectOptions.value = projectCatalog.jiraProjects
        .filter((project) => hasProjectJiraRole(project.roles.jira, 'operator'))
        .map((project) => ({ label: project.name, value: project.slug }))
      if (projectOptions.value.length === 1) {
        selectedProjectSlugs.value = [projectOptions.value[0].value]
      }
    } catch (error) {
      if (!isCurrent()) return
      projectOptions.value = []
      window.$message.error(formatApiError(error))
    } finally {
      if (isCurrent()) projectsLoading.value = false
    }
  }

  return {
    draft,
    busy,
    form,
    preflight,
    eligible,
    locked,
    publishable,
    requiresReconciliation,
    canEdit,
    canApprove,
    canPreflight,
    canPublish,
    canPrepare,
    isJiraConnected,
    statusType,
    dirty,
    hasSaveConflict,
    projectOptions,
    projectsLoading,
    publicationJob,
    selectedProjectSlugs,
    prepareDraft,
    saveDraft,
    keepEditsAfterConflict,
    reloadSavedDraft,
    approveDraft,
    checkPreflight,
    setExtraField,
    publishDraft
  }
}

function draftFingerprint(draft: JiraIssueDraft): string {
  return JSON.stringify([draft.project_key, draft.summary, draft.description, draft.extra_fields])
}

function formFingerprint(form: {
  project_key: string
  summary: string
  description: string
  extra_fields: Record<string, JiraFieldValue>
}): string {
  return JSON.stringify([form.project_key, form.summary, form.description, form.extra_fields])
}

function draftStatusType(draft: JiraIssueDraft | null) {
  if (draft?.status === 'published') return 'success'
  if (draft?.status === 'failed') return 'error'
  if (draft?.status === 'approved') return 'warning'
  return 'info'
}
