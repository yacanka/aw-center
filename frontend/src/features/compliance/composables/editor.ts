import { computed, onBeforeUnmount, ref, type Ref } from 'vue'
import type { FormInst, FormRules } from 'naive-ui'
import type { ICompDoc, IHistory } from '@/features/compliance/models/compdocs'
import { validateForm } from '@/shared/composables/forms'
import { RequestError } from '@/shared/composables/promise'
import { shouldLoadCompdocHistory } from '@/features/compliance/api/compdocHistory'
import {
  buildCompdocCreatePayload,
  buildCompdocUpdatePayload
} from '@/features/compliance/api/compdocPayload'
import {
  createCoverPageAllocation,
  fetchCoverPageAllocation,
  fetchExistingCoverPageAllocation,
  fetchNumberingOptions,
  resumeCoverPageAllocation,
  type CoverPageAllocation
} from '@/features/compliance/api/compdocNumbering'
import { formatApiError } from '@/shared/api/apiError'
import { isoToTurkishDateTime } from '@/shared/utils/time'
import { useNumberingContext } from './numberingContext'
import { useCompdocController } from '@/features/compliance/composables/compdocController'

const ALLOCATION_REFRESH_MILLISECONDS = 1500

export function useCompDocEditor(canEdit: Ref<boolean>) {
  const compdocStore = useCompdocController()
  const formRef = ref<FormInst | null>(null)
  const showModal = ref(false)
  const compdoc = ref<ICompDoc>({} as ICompDoc)
  const originalCompdoc = ref<ICompDoc>({} as ICompDoc)
  let disposed = false
  let editorRevision = 0
  const popupMode = ref<string | null>(null)
  const numberingAvailable = ref(false)
  const numberingFormats = ref<string[]>([])
  const numberingFormat = ref<string | null>(null)
  const numberSource = ref<'manual' | 'numarator'>('manual')
  const allocation = ref<CoverPageAllocation | null>(null)
  const numberingContext = useNumberingContext(
    computed(() => compdocStore.getProjectName),
    numberingFormat,
    computed(() => showModal.value && numberSource.value === 'numarator'),
    computed(() => allocation.value?.context_data),
    computed(() => [compdoc.value])
  )
  const allocationOperationId = ref('')
  const allocationSubmitting = ref(false)
  const allocationPollError = ref('')
  const allocationTimer = ref<number | undefined>()
  const readonly = computed(() => popupMode.value === 'view')
  const formReadonly = computed(
    () => readonly.value || allocationSubmitting.value || Boolean(allocation.value)
  )
  const allocationActive = computed(() => {
    if (allocationSubmitting.value) return true
    if (allocationPollError.value) return false
    const jobStatus = allocation.value?.job?.status
    return jobStatus === 'queued' || jobStatus === 'running' || jobStatus === 'cancel_requested'
  })
  const allocationFailed = computed(() => {
    const jobStatus = allocation.value?.job?.status
    return (
      Boolean(allocationPollError.value) ||
      jobStatus === 'failed' ||
      jobStatus === 'reconciliation_required' ||
      jobStatus === 'cancelled'
    )
  })
  const allocationMessage = computed(() => {
    if (!allocation.value) return ''
    if (allocationPollError.value)
      return `${allocationPollError.value} Retry to reload the allocation status.`
    if (allocation.value.status === 'completed') return 'Cover page number assigned.'
    if (allocationFailed.value) {
      return (
        allocation.value.error_detail ||
        allocation.value.job?.message ||
        'Allocation needs attention.'
      )
    }
    return allocation.value.job?.message || 'Cover page number allocation queued.'
  })
  const rules = computed<FormRules>(() => ({
    ata: [
      {
        validator: () => !compdoc.value.ata || Boolean(compdoc.value.panel),
        message: 'Select an ATA assigned to the selected panel.',
        trigger: ['change', 'blur']
      }
    ],
    name: [
      { required: true, whitespace: true, message: 'Name is required.', trigger: ['blur', 'input'] }
    ],
    cover_page_no:
      numberSource.value === 'numarator'
        ? []
        : [
            {
              required: true,
              whitespace: true,
              message: 'Cover page number is required.',
              trigger: ['blur', 'input']
            }
          ]
  }))
  const isDirty = computed(
    () => !readonly.value && JSON.stringify(compdoc.value) !== JSON.stringify(originalCompdoc.value)
  )

  function openModal(value: ICompDoc, mode: string): void {
    editorRevision += 1
    stopAllocationRefresh()
    popupMode.value = mode
    const draft = JSON.parse(JSON.stringify(value)) as ICompDoc
    originalCompdoc.value = { ...draft }
    compdoc.value = { ...draft }
    allocation.value = null
    allocationPollError.value = ''
    allocationSubmitting.value = false
    allocationOperationId.value = crypto.randomUUID()
    numberSource.value = 'manual'
    numberingAvailable.value = false
    numberingFormats.value = []
    numberingFormat.value = null
    showModal.value = true
    if (mode === 'new' || !draft.cover_page_no || canEdit.value) void loadNumberingOptions()
  }

  function closeModal(): void {
    editorRevision += 1
    stopAllocationRefresh()
    showModal.value = false
  }

  function isCurrentEditor(revision: number): boolean {
    return !disposed && showModal.value && revision === editorRevision
  }

  function handleVisibilityChange(visible: boolean): void {
    if (
      !visible &&
      (allocationSubmitting.value || (allocation.value && allocation.value.status !== 'completed'))
    ) {
      window.$message.info('Finish or retry the cover page number allocation before closing.')
      return
    }
    if (visible || !isDirty.value) {
      if (visible) showModal.value = true
      else closeModal()
      return
    }
    window.$dialog.warning({
      title: 'Discard unsaved changes?',
      content: 'Your edits have not been saved.',
      positiveText: 'Discard',
      negativeText: 'Keep editing',
      onPositiveClick: closeModal
    })
  }

  async function save(): Promise<void> {
    if (readonly.value || !canEdit.value || allocationActive.value || allocation.value) return
    const revision = editorRevision
    if (!(await validateForm(formRef.value))) return
    if (!isCurrentEditor(revision)) return
    if (numberSource.value === 'numarator') {
      if (!numberingFormat.value || !numberingFormats.value.includes(numberingFormat.value)) {
        window.$message.error('Select a cover page number format.')
        return
      }
      if (!numberingContext.valid.value) {
        window.$message.error('Load and complete the number format fields.')
        return
      }
      await startAllocation()
      return
    }
    if (popupMode.value === 'new') {
      await compdocStore.createCompdoc(compdoc.value)
      if (isCurrentEditor(revision)) closeModal()
      return
    }
    await update()
  }

  async function loadNumberingOptions(): Promise<void> {
    const revision = editorRevision
    const documentId = popupMode.value !== 'new' && canEdit.value ? compdoc.value.id : undefined
    allocationSubmitting.value = true
    try {
      const [options, pending] = await Promise.all([
        fetchNumberingOptions(compdocStore.getProjectName),
        documentId
          ? fetchExistingCoverPageAllocation(compdocStore.getProjectName, documentId)
          : Promise.resolve(null)
      ])
      if (!isCurrentEditor(revision)) return
      numberingAvailable.value = options.available
      numberingFormats.value = options.formats
      numberingFormat.value = options.formats.length === 1 ? options.formats[0] : null
      if (pending) {
        allocation.value = pending
        numberSource.value = 'numarator'
        numberingFormat.value = pending.format_code
        handleAllocationState()
      }
    } catch (error) {
      if (!isCurrentEditor(revision)) return
      numberingAvailable.value = false
      window.$message.error(formatApiError(error))
    } finally {
      if (isCurrentEditor(revision)) allocationSubmitting.value = false
    }
  }

  async function startAllocation(): Promise<void> {
    if (allocationSubmitting.value) return
    const revision = editorRevision
    allocationSubmitting.value = true
    try {
      const created = await createCoverPageAllocation(
        compdocStore.getProjectName,
        allocationOperationId.value,
        popupMode.value === 'new'
          ? buildCompdocCreatePayload(compdoc.value)
          : buildCompdocUpdatePayload(compdoc.value),
        popupMode.value === 'new' ? undefined : compdoc.value.id,
        numberingFormat.value || undefined,
        numberingContext.payload.value
      )
      if (!isCurrentEditor(revision)) return
      allocation.value = created
      handleAllocationState()
    } catch (error) {
      if (isCurrentEditor(revision)) window.$message.error(formatApiError(error))
    } finally {
      if (isCurrentEditor(revision)) allocationSubmitting.value = false
    }
  }

  async function retryAllocation(): Promise<void> {
    if (!allocation.value || allocationSubmitting.value) return
    const revision = editorRevision
    allocationSubmitting.value = true
    try {
      if (allocationPollError.value) {
        await refreshAllocation()
        return
      }
      const resumed = await resumeCoverPageAllocation(compdocStore.getProjectName, allocation.value)
      if (!isCurrentEditor(revision)) return
      allocation.value = resumed
      handleAllocationState()
    } catch (error) {
      if (!isCurrentEditor(revision)) return
      // A lost response may hide a resumed attempt with a newer version.
      allocationPollError.value = formatApiError(error)
      window.$message.error(allocationPollError.value)
    } finally {
      if (isCurrentEditor(revision)) allocationSubmitting.value = false
    }
  }

  function scheduleAllocationRefresh(): void {
    stopAllocationRefresh()
    const status = allocation.value?.job?.status
    if (
      isCurrentEditor(editorRevision) &&
      !allocationPollError.value &&
      (status === 'queued' || status === 'running' || status === 'cancel_requested')
    ) {
      allocationTimer.value = window.setTimeout(refreshAllocation, ALLOCATION_REFRESH_MILLISECONDS)
    }
  }

  async function refreshAllocation(): Promise<void> {
    if (!allocation.value) return
    const revision = editorRevision
    try {
      const refreshed = await fetchCoverPageAllocation(
        compdocStore.getProjectName,
        allocation.value.id
      )
      if (!isCurrentEditor(revision)) return
      allocation.value = refreshed
      allocationPollError.value = ''
      handleAllocationState()
    } catch (error) {
      if (!isCurrentEditor(revision)) return
      allocationPollError.value = formatApiError(error)
      window.$message.error(allocationPollError.value)
      stopAllocationRefresh()
    }
  }

  function handleAllocationState(): void {
    if (allocation.value?.status === 'completed' && allocation.value.document) {
      if (popupMode.value === 'new') compdocStore.acceptCreatedCompdoc(allocation.value.document)
      else compdocStore.acceptUpdatedCompdoc(allocation.value.document)
      window.$message.success(`Cover page ${allocation.value.number} assigned.`)
      closeModal()
      return
    }
    scheduleAllocationRefresh()
  }

  function stopAllocationRefresh(): void {
    if (allocationTimer.value) window.clearTimeout(allocationTimer.value)
    allocationTimer.value = undefined
  }

  onBeforeUnmount(() => {
    disposed = true
    editorRevision += 1
    stopAllocationRefresh()
  })

  async function update(): Promise<void> {
    const revision = editorRevision
    const documentId = compdoc.value.id
    if (!documentId) {
      window.$message.error('Document identifier is missing.')
      return
    }
    try {
      await compdocStore.updateCompdoc(documentId, buildCompdocUpdatePayload(compdoc.value))
      if (isCurrentEditor(revision)) closeModal()
    } catch (error) {
      if (isCurrentEditor(revision)) handleUpdateError(error, documentId)
    }
  }

  function handleUpdateError(error: unknown, documentId: string): void {
    if (error instanceof RequestError && error.status === 409) {
      showConflictDialog(documentId)
    } else if (error instanceof RequestError && error.errors) {
      window.$message.error(formatFieldErrors(error.errors))
    }
  }

  function showConflictDialog(documentId: string): void {
    const draft = compdoc.value
    window.$dialog.warning({
      title: 'Document changed',
      content: 'Reload the latest version as a comparison baseline while keeping your draft.',
      positiveText: 'Reload and compare',
      negativeText: 'Keep current draft',
      onPositiveClick: () => reloadBaseline(documentId, draft)
    })
  }

  async function reloadBaseline(documentId: string, draft: ICompDoc): Promise<void> {
    const isCurrent = () =>
      !disposed && showModal.value && compdoc.value === draft && draft.id === documentId
    if (!isCurrent()) return
    const latest = await compdocStore.fetchCompdoc(documentId)
    if (!isCurrent()) return
    originalCompdoc.value = JSON.parse(JSON.stringify(latest)) as ICompDoc
    compdoc.value.version = latest.version
    // A cover has its own CAS version; never apply it to another number in the user's draft.
    compdoc.value.cover_page_version =
      compdoc.value.cover_page_no.trim() === latest.cover_page_no.trim()
        ? latest.cover_page_version
        : undefined
    window.$message.info('Latest values loaded as the comparison baseline.')
  }

  function setUpdateMode(): void {
    if (canEdit.value) popupMode.value = 'update'
  }

  async function loadHistory(value: { expanded?: boolean }): Promise<void> {
    if (!shouldLoadCompdocHistory(compdoc.value, value.expanded) || !compdoc.value.id) return
    const history = await compdocStore.fetchHistory(compdoc.value.id)
    compdoc.value.history = history.map(formatHistoryDate)
  }

  return {
    compdoc,
    allocationActive,
    allocationFailed,
    allocationMessage,
    formRef,
    formReadonly,
    handleVisibilityChange,
    loadHistory,
    openModal,
    originalCompdoc,
    numberingContext,
    numberingAvailable,
    numberingFormats,
    numberingFormat,
    numberSource,
    popupMode,
    rules,
    retryAllocation,
    save,
    setUpdateMode,
    showModal
  }
}

function formatFieldErrors(errors: unknown): string {
  if (!errors || typeof errors !== 'object') return 'Review the highlighted fields.'
  return Object.entries(errors as Record<string, unknown>)
    .map(([field, value]) => `${field}: ${String(value)}`)
    .join(' · ')
    .slice(0, 500)
}

function formatHistoryDate(item: IHistory): IHistory {
  return { ...item, history_date: isoToTurkishDateTime(item.history_date) }
}
