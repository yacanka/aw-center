import { computed, onMounted, reactive, ref, watch } from 'vue'
import { formatApiError } from '@/shared/api/apiError'
import { useSessionStore } from '@/features/session/stores/session'
import { usePageJob } from '@/features/jobs/composables/usePageJob'
import {
  enqueueDoorsRequirementLink,
  fetchDoorsRequirementLinkResult,
  fetchDoorsStatus,
  type DoorsLinkDirection,
  type DoorsRequirementLinkInput,
  type DoorsRequirementLinkResult,
  type DoorsStatus
} from '@/features/integrations/api/doorsAutomation'

const STORAGE_KEY = 'poc_linker'

export function usePocLinker() {
  const session = useSessionStore()
  const form = reactive<DoorsRequirementLinkInput>({
    ref_module_name: '',
    target_module_name: '',
    link_module_name: '',
    ref_attr_poc: '',
    ref_attr_req: '',
    target_attr_poc: '',
    start_index: 0,
    text_length: -1,
    direction: 'ref2tar',
    activeness: false
  })
  const testText = ref('This is test text')
  const bridge = ref<DoorsStatus | null>(null)
  const statusLoading = ref(false)
  const queueing = ref(false)
  const result = ref<DoorsRequirementLinkResult | null>(null)
  const resultLoading = ref(false)
  const resultJobId = ref('')
  let pendingAttempt: { fingerprint: string; key: string } | null = null
  const pageJob = usePageJob('poc_linker_job')

  const canCreateLinks = computed(() =>
    Boolean(session.getUser.is_staff || session.getUser.is_superuser)
  )
  const validInput = computed(
    () =>
      requiredValues().every(Boolean) &&
      Number.isInteger(form.start_index) &&
      form.start_index >= 0 &&
      Number.isInteger(form.text_length) &&
      form.text_length >= -1
  )
  const canQueue = computed(
    () =>
      Boolean(bridge.value?.available) &&
      validInput.value &&
      !queueing.value &&
      !pageJob.active.value &&
      (!form.activeness || canCreateLinks.value)
  )
  const cropPreview = computed(() => {
    const start = form.start_index
    return form.text_length < 0
      ? testText.value.slice(start)
      : testText.value.slice(start, start + form.text_length)
  })
  const readinessMessage = computed(() => {
    if (!bridge.value) return 'Windows automation availability has not been verified.'
    if (!bridge.value.configured) return 'The outbound Windows bridge is not configured.'
    if (!bridge.value.available) return 'No authenticated Windows automation agent is live.'
    return `${bridge.value.active_agents} Windows automation agent(s) available.`
  })
  const visibleGroups = computed(() => result.value?.groups.slice(0, 200) || [])

  onMounted(() => {
    restoreForm()
    void loadStatus()
  })
  watch(pageJob.job, (job) => {
    if (job?.status === 'succeeded' && job.id !== resultJobId.value) void loadResult(job)
  })

  async function loadStatus(): Promise<void> {
    statusLoading.value = true
    try {
      bridge.value = await fetchDoorsStatus()
    } catch (error) {
      bridge.value = null
      window.$message.error(formatApiError(error))
    } finally {
      statusLoading.value = false
    }
  }

  async function queue(): Promise<void> {
    if (!canQueue.value) return
    const input = normalizedInput()
    const fingerprint = JSON.stringify(input)
    if (pendingAttempt?.fingerprint !== fingerprint) {
      pendingAttempt = { fingerprint, key: crypto.randomUUID() }
    }
    queueing.value = true
    result.value = null
    try {
      const job = await enqueueDoorsRequirementLink(input, pendingAttempt.key)
      pendingAttempt = null
      localStorage.setItem(STORAGE_KEY, JSON.stringify(input))
      pageJob.setJob(job)
      window.$message.success(
        input.activeness ? 'Requirement linking queued.' : 'Requirement link preview queued.'
      )
    } catch (error) {
      window.$message.error(formatApiError(error))
    } finally {
      queueing.value = false
    }
  }

  async function loadResult(job: NonNullable<typeof pageJob.job.value>): Promise<void> {
    resultLoading.value = true
    try {
      result.value = await fetchDoorsRequirementLinkResult(job)
      resultJobId.value = job.id
    } catch (error) {
      pageJob.errorMessage.value = formatApiError(error)
    } finally {
      resultLoading.value = false
    }
  }

  function normalizedInput(): DoorsRequirementLinkInput {
    return {
      ...form,
      ref_module_name: form.ref_module_name.trim(),
      target_module_name: form.target_module_name.trim(),
      link_module_name: form.link_module_name.trim(),
      ref_attr_poc: form.ref_attr_poc.trim(),
      ref_attr_req: form.ref_attr_req.trim(),
      target_attr_poc: form.target_attr_poc.trim()
    }
  }

  function requiredValues(): string[] {
    return [
      form.ref_module_name,
      form.target_module_name,
      form.link_module_name,
      form.ref_attr_poc,
      form.ref_attr_req,
      form.target_attr_poc
    ].map((value) => value.trim())
  }

  function restoreForm(): void {
    try {
      const stored: unknown = JSON.parse(localStorage.getItem(STORAGE_KEY) || 'null')
      const restored = normalizeStoredInput(stored)
      if (restored) Object.assign(form, restored)
    } catch {
      localStorage.removeItem(STORAGE_KEY)
    }
  }

  return {
    ...pageJob,
    bridge,
    canCreateLinks,
    canQueue,
    cropPreview,
    form,
    loadStatus,
    queue,
    queueing,
    readinessMessage,
    result,
    resultLoading,
    statusLoading,
    testText,
    visibleGroups
  }
}

function normalizeStoredInput(value: unknown): DoorsRequirementLinkInput | null {
  if (!value || typeof value !== 'object') return null
  const input = value as Partial<Record<keyof DoorsRequirementLinkInput, unknown>>
  const strings = [
    input.ref_module_name,
    input.target_module_name,
    input.link_module_name,
    input.ref_attr_poc,
    input.ref_attr_req,
    input.target_attr_poc
  ]
  const startIndex = Number(input.start_index)
  const textLength = Number(input.text_length)
  const active =
    typeof input.activeness === 'boolean'
      ? input.activeness
      : input.activeness === 'true'
        ? true
        : input.activeness === 'false'
          ? false
          : null
  if (
    !strings.every((item) => typeof item === 'string') ||
    !Number.isInteger(startIndex) ||
    startIndex < 0 ||
    !Number.isInteger(textLength) ||
    textLength < -1 ||
    !['ref2tar', 'tar2ref'].includes(input.direction as DoorsLinkDirection) ||
    active === null
  ) {
    return null
  }
  return {
    ref_module_name: input.ref_module_name as string,
    target_module_name: input.target_module_name as string,
    link_module_name: input.link_module_name as string,
    ref_attr_poc: input.ref_attr_poc as string,
    ref_attr_req: input.ref_attr_req as string,
    target_attr_poc: input.target_attr_poc as string,
    start_index: startIndex,
    text_length: textLength,
    direction: input.direction as DoorsLinkDirection,
    activeness: active
  }
}
