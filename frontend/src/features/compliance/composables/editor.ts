import { computed, ref, type Ref } from 'vue'
import type { FormInst, FormRules } from 'naive-ui'
import type { ICompDoc, IHistory } from '@/features/compliance/models/compdocs'
import { validateForm } from '@/shared/composables/forms'
import { RequestError } from '@/shared/composables/promise'
import { shouldLoadCompdocHistory } from '@/features/compliance/api/compdocHistory'
import { buildCompdocUpdatePayload } from '@/features/compliance/api/compdocPayload'
import { isoToTurkishDateTime } from '@/shared/utils/time'
import { useCompdocController } from '@/features/compliance/composables/compdocController'

const rules: FormRules = {
  name: [{ required: true, trigger: 'blur' }],
  panel: [{ required: true, trigger: 'blur' }],
  cover_page_no: [{ required: true, trigger: 'blur' }]
}

export function useCompDocEditor(canEdit: Ref<boolean>) {
  const compdocStore = useCompdocController()
  const formRef = ref<FormInst | null>(null)
  const showModal = ref(false)
  const compdoc = ref<ICompDoc>({} as ICompDoc)
  const originalCompdoc = ref<ICompDoc>({} as ICompDoc)
  const popupMode = ref<string | null>(null)
  const hasExtraFields = ref(false)
  const readonly = computed(() => popupMode.value === 'view')
  const isDirty = computed(
    () => !readonly.value && JSON.stringify(compdoc.value) !== JSON.stringify(originalCompdoc.value)
  )

  function openModal(value: ICompDoc, mode: string): void {
    popupMode.value = mode
    const draft = JSON.parse(JSON.stringify(value)) as ICompDoc
    originalCompdoc.value = { ...draft }
    compdoc.value = { ...draft }
    hasExtraFields.value = compdocStore.checkBonusFields()
    showModal.value = true
  }

  function closeModal(): void {
    showModal.value = false
  }

  function handleVisibilityChange(visible: boolean): void {
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
    if (!(await validateForm(formRef.value))) return
    if (popupMode.value === 'new') {
      await compdocStore.createCompdoc(compdoc.value)
      closeModal()
      return
    }
    await update()
  }

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
    formRef,
    handleVisibilityChange,
    hasExtraFields,
    loadHistory,
    openModal,
    originalCompdoc,
    popupMode,
    readonly,
    rules,
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
