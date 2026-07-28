import { computed, ref } from 'vue'
import type { ICompDoc } from '@/models/compdocs'
import type { useCompdocStore } from '@/stores/compdoc'

/** Coordinate selected-row, detail, and tracking workspaces. */
export function useCompdocWorkspace(store: ReturnType<typeof useCompdocStore>) {
  const selectedDocument = ref<ICompDoc | null>(null)
  const workspaceVisible = ref(false)
  const trackingVisible = ref(false)
  const activeDocument = computed(() => {
    const id = selectedDocument.value?.id
    return store.getCompdocs.find((document) => document.id === id) || selectedDocument.value
  })

  function openWorkspace(document: ICompDoc) {
    selectedDocument.value = document
    workspaceVisible.value = true
  }

  function openTracking(document: ICompDoc) {
    selectedDocument.value = document
    trackingVisible.value = true
  }

  function closeWorkspace() {
    workspaceVisible.value = false
    trackingVisible.value = false
    selectedDocument.value = null
  }

  function rowProps(document: ICompDoc) {
    return {
      class: selectedDocument.value?.id === document.id ? 'compdoc-row--selected' : '',
      tabindex: 0,
      'aria-label': `Open document workspace for ${document.name}`,
      onClick: () => (selectedDocument.value = document),
      onDblclick: () => openWorkspace(document),
      onKeydown: (event: KeyboardEvent) => {
        if (event.key === 'Enter') openWorkspace(document)
      }
    }
  }

  async function copyDocumentPath(document: ICompDoc) {
    if (!document.path) return
    try {
      await navigator.clipboard.writeText(document.path)
      window.$message.success('Reference path copied.')
    } catch {
      window.$message.error('Reference path could not be copied.')
    }
  }

  function confirmDocumentDeletion(document: ICompDoc) {
    window.$dialog.error({
      title: 'Delete compliance document',
      content: `Delete “${document.name}”? This action cannot be undone.`,
      positiveText: 'Delete document',
      negativeText: 'Cancel',
      onPositiveClick: () => deleteDocument(document)
    })
  }

  async function deleteDocument(document: ICompDoc) {
    if (!document.id) return
    try {
      await store.deleteCompdoc(document.id)
      closeWorkspace()
    } catch {
      // The shared request handler presents the recoverable API error.
    }
  }

  return {
    activeDocument,
    closeWorkspace,
    confirmDocumentDeletion,
    copyDocumentPath,
    openTracking,
    openWorkspace,
    rowProps,
    selectedDocument,
    trackingVisible,
    workspaceVisible
  }
}
