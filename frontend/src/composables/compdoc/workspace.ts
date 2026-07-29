import { computed, h, ref } from 'vue'
import { NInput } from 'naive-ui'
import type { ICompDoc } from '@/models/compdocs'
import type { useCompdocStore } from '@/stores/compdoc'

/** Coordinate the selected row and its document workspace. */
export function useCompdocWorkspace(store: ReturnType<typeof useCompdocStore>) {
  const selectedDocument = ref<ICompDoc | null>(null)
  const workspaceVisible = ref(false)
  const activeDocument = computed(() => {
    const id = selectedDocument.value?.id
    return store.getCompdocs.find((document) => document.id === id) || selectedDocument.value
  })

  function openWorkspace(document: ICompDoc) {
    selectedDocument.value = document
    workspaceVisible.value = true
  }

  function closeWorkspace() {
    workspaceVisible.value = false
    selectedDocument.value = null
  }

  function rowProps(document: ICompDoc) {
    return {
      class: selectedDocument.value?.id === document.id ? 'compdoc-row--selected' : '',
      tabindex: 0,
      title: `Double-click to open ${document.name}`,
      'aria-label': `Double-click or press Enter to open document workspace for ${document.name}`,
      onDblclick: () => openWorkspace(document),
      onKeydown: (event: KeyboardEvent) => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault()
          openWorkspace(document)
        }
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
    const reason = ref('')
    window.$dialog.error({
      title: 'Archive compliance document',
      content: () =>
        h(NInput, {
          value: reason.value,
          placeholder: `Reason for archiving “${document.name}” (optional)`,
          maxlength: 255,
          'onUpdate:value': (value: string) => (reason.value = value)
        }),
      positiveText: 'Archive document',
      negativeText: 'Cancel',
      onPositiveClick: () => archiveDocument(document, reason.value)
    })
  }

  async function archiveDocument(document: ICompDoc, reason: string) {
    if (!document.id || !document.source_history_id) return
    try {
      await store.archiveCompdoc(document.id, document.source_history_id, reason)
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
    openWorkspace,
    rowProps,
    selectedDocument,
    workspaceVisible
  }
}
