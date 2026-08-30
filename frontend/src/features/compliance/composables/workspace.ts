import { computed, h, ref } from 'vue'
import { NInput } from 'naive-ui'
import type { ICompDoc } from '@/features/compliance/models/compdocs'
import type { CompdocController } from '@/features/compliance/composables/compdocController'

/** Coordinate the selected row and its document workspace. */
export function useCompdocWorkspace(store: CompdocController) {
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
    const restoring = Boolean(document.is_archived)
    window.$dialog.error({
      title: restoring ? 'Restore compliance document' : 'Archive compliance document',
      content: () =>
        h(NInput, {
          value: reason.value,
          placeholder: `Reason for ${restoring ? 'restoring' : 'archiving'} “${document.name}” (optional)`,
          maxlength: 255,
          'onUpdate:value': (value: string) => (reason.value = value)
        }),
      positiveText: restoring ? 'Restore document' : 'Archive document',
      negativeText: 'Cancel',
      onPositiveClick: () => changeArchiveState(document, reason.value)
    })
  }

  async function changeArchiveState(document: ICompDoc, reason: string) {
    if (!document.id || !document.version) return
    try {
      if (document.is_archived) {
        await store.restoreCompdoc(document.id, document.version, reason)
      } else {
        await store.archiveCompdoc(document.id, document.version, reason)
      }
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
