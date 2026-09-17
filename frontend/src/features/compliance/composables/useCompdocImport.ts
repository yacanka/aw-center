import { computed, ref, watch } from 'vue'
import type { UploadCustomRequestOptions } from 'naive-ui'
import { formatApiError, getApiErrorCode } from '@/shared/api/apiError'
import {
  confirmCompdocImport,
  previewCompdocImport,
  type ImportInvalidDocument,
  type ImportPreview
} from '@/features/compliance/api/compdocImports'
import { useCompdocController } from '@/features/compliance/composables/compdocController'
import { popupStore } from '@/app/stores/popupStore'
import { isPlainObject } from '@/shared/utils/general'

const REFRESHABLE_CODES = new Set(['VERSION_CONFLICT', 'COMPDOC_IMPORT_PREVIEW_EXPIRED'])

/** Coordinate the preview-confirm workflow for one CompDoc workbook import. */
export function useCompdocImport(uploadUrl: () => string) {
  const showModal = ref(false)
  const showPreviewModal = ref(false)
  const confirmingImport = ref(false)
  const validating = ref(false)
  const mode = ref<'automatic' | 'manual'>('automatic')
  const mapping = ref<Record<string, string>>({})
  const source = ref<ImportPreview | null>(null)
  const previewNotice = ref('')
  const pendingFile = ref<File | null>(null)
  const preview = ref<ImportPreview | null>(null)
  let requestSequence = 0
  const busy = computed(() => validating.value || confirmingImport.value)
  const canConfirm = computed(
    () =>
      !busy.value &&
      Boolean(preview.value?.confirmation_token) &&
      !preview.value?.missing_columns.length
  )
  watch(
    [mode, mapping],
    () => {
      if (!source.value) return
      requestSequence++
      validating.value = false
      preview.value = null
      previewNotice.value = 'Linking changed. Validate the import to review the updated preview.'
    },
    { deep: true, flush: 'sync' }
  )
  const callbacks = ref<Pick<UploadCustomRequestOptions, 'onFinish' | 'onError'> | null>(null)
  const store = useCompdocController()

  function setActive(show: boolean) {
    showModal.value = show
  }

  async function handleUploadReq(options: UploadCustomRequestOptions) {
    if (!options.file.file) return
    if (busy.value) return
    resetUploadState()
    setActive(true)
    pendingFile.value = options.file.file
    callbacks.value = { onFinish: options.onFinish, onError: options.onError }
    await loadPreview(options.file.file)
  }

  async function loadPreview(file: File, refreshed = false) {
    const sequence = ++requestSequence
    const path = uploadUrl()
    const selectedMapping = mode.value === 'manual' ? { ...mapping.value } : undefined
    validating.value = true
    preview.value = null
    window.$loadingBar.start()
    try {
      const result = await previewCompdocImport(path, file, selectedMapping)
      if (sequence !== requestSequence || path !== uploadUrl()) return
      if (!source.value) {
        mapping.value = Object.fromEntries(
          result.mapped_columns.map((row) => [row.source, row.target])
        )
        source.value = result
      }
      preview.value = result
      previewNotice.value = refreshed
        ? 'Database records changed after your review. The preview was refreshed; review it again.'
        : ''
      setActive(false)
      showPreviewModal.value = true
      window.$loadingBar.finish()
    } catch (error: unknown) {
      if (sequence !== requestSequence || path !== uploadUrl()) return
      if (!source.value) callbacks.value?.onError()
      showUploadError(error)
    } finally {
      if (sequence === requestSequence) validating.value = false
    }
  }

  async function validateImport() {
    if (!pendingFile.value || busy.value) return
    await loadPreview(pendingFile.value)
  }

  async function confirmImport() {
    if (!canConfirm.value || !pendingFile.value || !preview.value?.confirmation_token) return
    confirmingImport.value = true
    window.$loadingBar.start()
    try {
      await submitImport(pendingFile.value, preview.value.confirmation_token)
    } catch (error: unknown) {
      await recoverConfirmation(error)
    } finally {
      confirmingImport.value = false
    }
  }

  async function submitImport(file: File, token: string) {
    const result = await confirmCompdocImport(
      uploadUrl(),
      file,
      token,
      mode.value === 'manual' ? { ...mapping.value } : undefined
    )
    window.$loadingBar.finish()
    callbacks.value?.onFinish()
    showUploadSuccess(result.detail, result.invalid_documents)
    await store.fetchCompdocs()
    resetUploadState()
  }

  async function recoverConfirmation(error: unknown) {
    if (pendingFile.value && REFRESHABLE_CODES.has(getApiErrorCode(error) || '')) {
      await loadPreview(pendingFile.value, true)
      return
    }
    callbacks.value?.onError()
    showUploadError(error)
  }

  function cancelPreview() {
    if (confirmingImport.value) return
    callbacks.value?.onError()
    resetUploadState()
  }

  function resetUploadState() {
    requestSequence++
    source.value = null
    mode.value = 'automatic'
    mapping.value = {}
    validating.value = false
    pendingFile.value = null
    preview.value = null
    previewNotice.value = ''
    callbacks.value = null
    showPreviewModal.value = false
    setActive(false)
  }

  return {
    mode,
    mapping,
    source,
    validating,
    busy,
    canConfirm,
    validateImport,
    showModal,
    showPreviewModal,
    confirmingImport,
    previewNotice,
    preview,
    setActive,
    handleUploadReq,
    confirmImport,
    cancelPreview
  }
}

function showUploadSuccess(message: string, invalidDocuments?: ImportInvalidDocument[]) {
  window.$notification.success({ title: 'Success', description: message, duration: 3000 })
  if (invalidDocuments?.length) showInvalidDocuments(invalidDocuments)
}

function showUploadError(error: unknown) {
  window.$loadingBar.error()
  window.$notification.error({
    title: 'Error',
    description: `Error while uploading file: ${formatApiError(error)}`
  })
}

function showInvalidDocuments(documents: ImportInvalidDocument[]) {
  const result = documents.map(formatInvalidDocument).join('\n')
  popupStore().open('Some documents cannot be imported', result)
}

function formatInvalidDocument(document: ImportInvalidDocument) {
  const errorText = isPlainObject(document.fields)
    ? Object.entries(document.fields)
        .map(([key, value]) => `${key}: ${value}`)
        .join('\n')
    : String(document.fields)
  const rowLabel = document.row ? `[Row] ${document.row}\n` : ''
  return `${rowLabel}[Code] ${document.code}\n[Error] ${errorText}\n`
}
