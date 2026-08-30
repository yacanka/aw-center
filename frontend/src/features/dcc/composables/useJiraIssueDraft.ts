import { computed, reactive, ref, watch } from 'vue'
import type { JiraFieldValue } from '@/features/dcc/models/jira'
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
} from '@/features/dcc/api/jiraIssueDrafts'
import { useDccStore } from '@/features/dcc/stores/dcc'
import { useProjectCatalogStore } from '@/features/projects/stores/projectCatalog'
import { hasProjectDccRole } from '@/features/projects/models/projectRegistry'

/** Coordinate the owner-visible JIRA draft review lifecycle for one selected job. */
export function useJiraIssueDraft(selectedJob: () => Job) {
  const dccStore = useDccStore()
  const projectCatalog = useProjectCatalogStore()
  const draft = ref<JiraIssueDraft | null>(null)
  const busy = ref(false)
  const preflight = ref<JiraIssueDraftPreflight | null>(null)
  const publicationJob = ref<Job | null>(null)
  const projectOptions = ref<Array<{ label: string; value: string }>>([])
  const selectedProjectSlugs = ref<string[]>([])
  const projectsLoading = ref(false)
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
  const canEdit = computed(() => Boolean(draft.value?.allowed_actions.edit))
  const canApprove = computed(() => Boolean(draft.value?.allowed_actions.approve))
  const canPreflight = computed(() => Boolean(draft.value?.allowed_actions.preflight))
  const canPublish = computed(() => Boolean(draft.value?.allowed_actions.publish))
  const canPrepare = computed(() => selectedProjectSlugs.value.length > 0)
  const isJiraConnected = computed(() => dccStore.isJiraConnected)
  const statusType = computed(() => draftStatusType(draft.value))
  const dirty = computed(
    () => draft.value != null && draftFingerprint(draft.value) != formFingerprint(form)
  )

  watch(() => selectedJob().id, loadExistingDraft, { immediate: true })
  void dccStore.fetchJiraConnection().catch(() => undefined)

  async function loadExistingDraft(): Promise<void> {
    resetPanel()
    const reference = selectedJob().jira_draft
    if (!reference) {
      await loadProjectOptions()
      return
    }
    busy.value = true
    try {
      setDraft(await fetchJiraIssueDraft(reference.id))
    } catch (error) {
      window.$message.error(formatApiError(error))
    } finally {
      busy.value = false
    }
  }

  async function prepareDraft(): Promise<void> {
    const jobId = selectedJob().id
    if (!selectedProjectSlugs.value.length) return
    await run(
      async () => setDraft(await createJiraIssueDraft(jobId, [...selectedProjectSlugs.value])),
      'JIRA draft is ready.'
    )
  }

  async function saveDraft(): Promise<void> {
    const current = draft.value
    if (!current) return
    const values = { ...form, version: current.version }
    await run(async () => setDraft(await updateJiraIssueDraft(current.id, values)), 'Draft saved.')
  }

  async function approveDraft(): Promise<void> {
    const current = draft.value
    if (!current) return
    await run(async () => setDraft(await approveJiraIssueDraft(current), true), 'Version approved.')
  }

  async function checkPreflight(): Promise<void> {
    const current = draft.value
    if (!current) return
    await run(async () => {
      preflight.value = await preflightJiraIssueDraft(current)
    }, 'JIRA requirements checked.')
  }

  function setExtraField(identifier: string, value: JiraFieldValue): void {
    form.extra_fields[identifier] = value
  }

  async function publishDraft(): Promise<void> {
    const current = draft.value
    if (!current) return
    await run(async () => {
      const fingerprint = `${current.id}:${current.version}:${current.status}`
      if (publicationAttempt?.fingerprint !== fingerprint) {
        publicationAttempt = { fingerprint, key: crypto.randomUUID() }
      }
      publicationJob.value = await publishJiraIssueDraft(current, publicationAttempt.key)
      try {
        setDraft(await fetchJiraIssueDraft(current.id), true)
      } catch {
        draft.value = {
          ...current,
          status: 'publishing',
          version: current.version + 1,
          publication_job: publicationJob.value.id
        }
      }
    }, 'JIRA publication job queued.')
  }

  async function run(action: () => Promise<void>, successMessage: string): Promise<void> {
    busy.value = true
    try {
      await action()
      window.$message.success(successMessage)
    } catch (error) {
      await recoverDraft()
      window.$message.error(formatApiError(error))
    } finally {
      busy.value = false
    }
  }

  async function recoverDraft(): Promise<void> {
    if (!draft.value) return
    try {
      setDraft(await fetchJiraIssueDraft(draft.value.id))
    } catch {
      draft.value = null
    }
  }

  function setDraft(value: JiraIssueDraft, preservePreflight = false): void {
    draft.value = value
    form.project_key = value.project_key
    form.summary = value.summary
    form.description = value.description
    form.extra_fields = { ...value.extra_fields }
    selectedProjectSlugs.value = [...value.project_slugs]
    if (!preservePreflight) preflight.value = null
  }

  function resetPanel(): void {
    draft.value = null
    preflight.value = null
    publicationJob.value = null
    publicationAttempt = null
  }

  async function loadProjectOptions(): Promise<void> {
    projectsLoading.value = true
    try {
      await projectCatalog.load()
      projectOptions.value = projectCatalog.dccProjects
        .filter((project) => hasProjectDccRole(project.roles.dcc, 'operator'))
        .map((project) => ({ label: project.name, value: project.slug }))
      if (projectOptions.value.length === 1) {
        selectedProjectSlugs.value = [projectOptions.value[0].value]
      }
    } catch (error) {
      projectOptions.value = []
      window.$message.error(formatApiError(error))
    } finally {
      projectsLoading.value = false
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
    canEdit,
    canApprove,
    canPreflight,
    canPublish,
    canPrepare,
    isJiraConnected,
    statusType,
    dirty,
    projectOptions,
    projectsLoading,
    publicationJob,
    selectedProjectSlugs,
    prepareDraft,
    saveDraft,
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
