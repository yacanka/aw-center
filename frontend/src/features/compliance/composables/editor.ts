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
import { useCompdocController } from '@/features/compliance/composables/compdocController'

const ALLOCATION_REFRESH_MILLISECONDS = 1500

export function useCompDocEditor(canEdit: Ref<boolean>) {
  const compdocStore = useCompdocController()
  const formRef = ref<FormInst | null>(null)
  const showModal = ref(false)
  const compdoc = ref<ICompDoc>({} as ICompDoc)
  const originalCompdoc = ref<ICompDoc>({} as ICompDoc)
  const popupMode = ref<string | null>(null)
  const hasExtraFields = ref(false)
  const numberingAvailable = ref(false)
  const numberingFormats = ref<string[]>([])
  const numberingFormat = ref<string | null>(null)
  const numberSource = ref<'manual' | 'numarator'>('manual')
  const allocation = ref<CoverPageAllocation | null>(null)
  const allocationOperationId = ref('')
  const allocationSubmitting = ref(false)
  const allocationTimer = ref<number | undefined>()
  const readonly = computed(() => popupMode.value === 'view')
  const formReadonly = computed(
    () => readonly.value || allocationSubmitting.value || Boolean(allocation.value)
  )
  const allocationActive = computed(() => {
    if (allocationSubmitting.value) return true
    const jobStatus = allocation.value?.job?.status
    return jobStatus === 'queued' || jobStatus === 'running' || jobStatus === 'cancel_requested'
  })
  const allocationFailed = computed(() => {
    const jobStatus = allocation.value?.job?.status
    return jobStatus === 'failed' || jobStatus === 'reconciliation_required'
  })
  const allocationMessage = computed(() => {
    if (!allocation.value) return ''
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
    name: [{ required: true, trigger: 'blur' }],
    cover_page_no: []
  }))
  const isDirty = computed(
    () => !readonly.value && JSON.stringify(compdoc.value) !== JSON.stringify(originalCompdoc.value)
  )

  function openModal(value: ICompDoc, mode: string): void {
    stopAllocationRefresh()
    popupMode.value = mode
    const draft = JSON.parse(JSON.stringify(value)) as ICompDoc
    originalCompdoc.value = { ...draft }
    compdoc.value = { ...draft }
    hasExtraFields.value = compdocStore.checkBonusFields()
    allocation.value = null
    allocationOperationId.value = crypto.randomUUID()
    numberSource.value = 'manual'
    numberingAvailable.value = false
    numberingFormats.value = []
    numberingFormat.value = null
    if (mode === 'new' || !draft.cover_page_no || canEdit.value) void loadNumberingOptions()
    showModal.value = true
  }

  function closeModal(): void {
    stopAllocationRefresh()
    showModal.value = false
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
      showModal.value = visible
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
    if (!(await validateForm(formRef.value))) return
    if (numberSource.value === 'numarator') {
      if (!numberingFormat.value || !numberingFormats.value.includes(numberingFormat.value)) {
        window.$message.error('Select a cover page number format.')
        return
      }
      await startAllocation()
      return
    }
    if (popupMode.value === 'new') {
      await compdocStore.createCompdoc(compdoc.value)
      closeModal()
      return
    }
    await update()
  }

  async function loadNumberingOptions(): Promise<void> {
    const operationId = allocationOperationId.value
    const documentId = popupMode.value !== 'new' && canEdit.value ? compdoc.value.id : undefined
    allocationSubmitting.value = true
    try {
      const [options, pending] = await Promise.all([
        fetchNumberingOptions(compdocStore.getProjectName),
        documentId
          ? fetchExistingCoverPageAllocation(compdocStore.getProjectName, documentId)
          : Promise.resolve(null)
      ])
      if (operationId !== allocationOperationId.value) return
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
      if (operationId !== allocationOperationId.value) return
      numberingAvailable.value = false
      window.$message.error(formatApiError(error))
    } finally {
      if (operationId === allocationOperationId.value) allocationSubmitting.value = false
    }
  }

  async function startAllocation(): Promise<void> {
    if (allocationSubmitting.value) return
    allocationSubmitting.value = true
    try {
      allocation.value = await createCoverPageAllocation(
        compdocStore.getProjectName,
        allocationOperationId.value,
        popupMode.value === 'new'
          ? buildCompdocCreatePayload(compdoc.value)
          : buildCompdocUpdatePayload(compdoc.value),
        popupMode.value === 'new' ? undefined : compdoc.value.id,
        numberingFormat.value || undefined
      )
      handleAllocationState()
    } catch (error) {
      window.$message.error(formatApiError(error))
    } finally {
      allocationSubmitting.value = false
    }
  }

  async function retryAllocation(): Promise<void> {
    if (!allocation.value || allocationSubmitting.value) return
    allocationSubmitting.value = true
    try {
      allocation.value = await resumeCoverPageAllocation(
        compdocStore.getProjectName,
        allocation.value
      )
      handleAllocationState()
    } catch (error) {
      window.$message.error(formatApiError(error))
    } finally {
      allocationSubmitting.value = false
    }
  }

  function scheduleAllocationRefresh(): void {
    stopAllocationRefresh()
    if (allocationActive.value && allocation.value) {
      allocationTimer.value = window.setTimeout(refreshAllocation, ALLOCATION_REFRESH_MILLISECONDS)
    }
  }

  async function refreshAllocation(): Promise<void> {
    if (!allocation.value) return
    try {
      allocation.value = await fetchCoverPageAllocation(
        compdocStore.getProjectName,
        allocation.value.id
      )
      handleAllocationState()
    } catch (error) {
      window.$message.error(formatApiError(error))
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

  onBeforeUnmount(stopAllocationRefresh)

  async function update(): Promise<void> {
    const documentId = compdoc.value.id
    if (!documentId) {
      window.$message.error('Document identifier is missing.')
      return
    }
    try {
      await compdocStore.updateCompdoc(documentId, buildCompdocUpdatePayload(compdoc.value))
      closeModal()
    } catch (error) {
      handleUpdateError(error, documentId)
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
    window.$dialog.warning({
      title: 'Document changed',
      content: 'Reload the latest version as a comparison baseline while keeping your draft.',
      positiveText: 'Reload and compare',
      negativeText: 'Keep current draft',
      onPositiveClick: () => reloadBaseline(documentId)
    })
  }

  async function reloadBaseline(documentId: string): Promise<void> {
    const latest = await compdocStore.fetchCompdoc(documentId)
    originalCompdoc.value = JSON.parse(JSON.stringify(latest)) as ICompDoc
    compdoc.value.version = latest.version
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
    hasExtraFields,
    loadHistory,
    openModal,
    originalCompdoc,
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
