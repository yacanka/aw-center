import { computed, reactive, ref, watch } from 'vue'
import type { JiraFieldValue } from '@/models/jira'
import { formatApiError } from '@/services/apiError'
import type { Job } from '@/services/jobs'
import {
  approveJiraIssueDraft,
  createJiraIssueDraft,
  fetchJiraIssueDraft,
  preflightJiraIssueDraft,
  publishJiraIssueDraft,
  updateJiraIssueDraft,
  type JiraIssueDraft,
  type JiraIssueDraftPreflight
} from '@/services/jiraIssueDrafts'
import { useUserStore } from '@/stores/user'
import { useDccStore } from '@/stores/dcc'

/** Coordinate the owner-visible JIRA draft review lifecycle for one selected job. */
export function useJiraIssueDraft(selectedJob: () => Job) {
  const userStore = useUserStore()
  const dccStore = useDccStore()
  const draft = ref<JiraIssueDraft | null>(null)
  const busy = ref(false)
  const sessionId = ref(dccStore.getSessionId)
  const preflight = ref<JiraIssueDraftPreflight | null>(null)
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
  const publishable = computed(() => ['approved', 'failed'].includes(draft.value?.status || ''))
  const canPublish = computed(() => userStore.hasEffectiveRole('dcc', 'publish_jiraissuedraft'))
  const statusType = computed(() => draftStatusType(draft.value))
  const dirty = computed(
    () => draft.value != null && draftFingerprint(draft.value) != formFingerprint(form)
  )

  watch(() => selectedJob().id, loadExistingDraft, { immediate: true })

  async function loadExistingDraft(): Promise<void> {
    resetPanel()
    const reference = selectedJob().jira_draft
    if (!reference) return
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
    await run(async () => setDraft(await createJiraIssueDraft(jobId)), 'JIRA draft is ready.')
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
      preflight.value = await preflightJiraIssueDraft(current, sessionId.value)
      dccStore.setSessionId(sessionId.value)
    }, 'JIRA requirements checked.')
  }

  function setExtraField(identifier: string, value: JiraFieldValue): void {
    form.extra_fields[identifier] = value
  }

  async function publishDraft(): Promise<void> {
    const current = draft.value
    if (!current) return
    await run(
      async () => setDraft(await publishJiraIssueDraft(current, sessionId.value)),
      'JIRA Task published.'
    )
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
    if (!preservePreflight) preflight.value = null
  }

  function resetPanel(): void {
    draft.value = null
    sessionId.value = dccStore.getSessionId
    preflight.value = null
  }

  return {
    draft,
    busy,
    sessionId,
    form,
    preflight,
    eligible,
    locked,
    publishable,
    canPublish,
    statusType,
    dirty,
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
