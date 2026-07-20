import { ref } from 'vue'
import type { UploadCustomRequestOptions } from 'naive-ui'
import { formatApiError, getApiErrorCode } from '@/services/apiError'
import {
  confirmCompdocImport,
  previewCompdocImport,
  type ImportInvalidDocument,
  type ImportPreview
} from '@/services/compdocImports'
import { useCompdocStore } from '@/stores/compdoc'
import { popupStore } from '@/stores/popupStore'
import { isPlainObject } from '@/utils/general'

const REFRESHABLE_CODES = new Set([
  'COMPDOC_IMPORT_DATABASE_CONFLICT',
  'COMPDOC_IMPORT_PREVIEW_EXPIRED'
])

/** Coordinate the preview-confirm workflow for one CompDoc workbook import. */
export function useCompdocImport(uploadUrl: () => string) {
  const showModal = ref(false)
  const showPreviewModal = ref(false)
  const confirmingImport = ref(false)
  const previewNotice = ref('')
  const pendingFile = ref<File | null>(null)
  const preview = ref<ImportPreview | null>(null)
  const callbacks = ref<Pick<UploadCustomRequestOptions, 'onFinish' | 'onError'> | null>(null)
  const store = useCompdocStore()

  function setActive(show: boolean) {
    showModal.value = show
  }

  async function handleUploadReq(options: UploadCustomRequestOptions) {
    if (!options.file.file) return
    pendingFile.value = options.file.file
    callbacks.value = { onFinish: options.onFinish, onError: options.onError }
    await loadPreview(options.file.file)
  }

  async function loadPreview(file: File, refreshed = false) {
    window.$loadingBar.start()
    try {
      preview.value = await previewCompdocImport(uploadUrl(), file)
      previewNotice.value = refreshed
        ? 'Database records changed after your review. The preview was refreshed; review it again.'
        : ''
      showPreviewModal.value = true
      window.$loadingBar.finish()
    } catch (error: unknown) {
      callbacks.value?.onError()
      showUploadError(error)
    }
  }

  async function confirmImport() {
    if (!pendingFile.value || !preview.value?.confirmation_token) return
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
    const result = await confirmCompdocImport(uploadUrl(), file, token)
    window.$loadingBar.finish()
    callbacks.value?.onFinish()
    showUploadSuccess(result.message, result.invalid_documents)
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
    callbacks.value?.onError()
    resetUploadState()
  }

  function resetUploadState() {
    pendingFile.value = null
    preview.value = null
    previewNotice.value = ''
    callbacks.value = null
    showPreviewModal.value = false
    setActive(false)
  }

  return {
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
  const errorText = isPlainObject(document.error)
    ? Object.entries(document.error as Record<string, unknown>)
        .map(([key, value]) => `${key}: ${value}`)
        .join('\n')
    : String(document.error)
  const rowLabel = document.row ? `[Row] ${document.row}\n` : ''
  return `${rowLabel}[Name] ${document.name}\n[Error] ${document.error_text || errorText}\n`
}
