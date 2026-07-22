<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import UpdateForm from '@/components/compdoc/CompDocPopup.vue'
import CompDocWorkspace from '@/components/compdoc/CompDocWorkspace.vue'
import UploadPopup from '@/components/compdoc/UploadPopup.vue'
import CompDocColumnSettings from '@/components/compdoc/CompDocColumnSettings.vue'
import CompDocTableToolbar from '@/components/compdoc/CompDocTableToolbar.vue'
import GraphComponent from '@/components/compdoc/Graph.vue'
import DownloadComponent from '@/components/Downloader.vue'
import { useCompdocStore } from '@/stores/compdoc'
import { useUserStore } from '@/stores/user'
import { createEmptyCompdoc } from '@/services/compdocCatalog'
import { useCompdocColumnOverrides } from '@/composables/compdoc/columnOverrides'
import { useCompdocIssueChecks } from '@/composables/compdoc/issueChecks'
import { useCompdocRemoteTable } from '@/composables/compdoc/remoteTable'
import type { ICompDoc } from '@/models/compdocs'
import './CompDocTable.css'

const route = useRoute()
const store = useCompdocStore()
const userStore = useUserStore()
const project = computed(() => String(route.params.project || ''))
const canView = permission('view')
const canAdd = permission('add')
const canChange = permission('change')
const canDelete = permission('delete')
const canImport = computed(() => canAdd.value && canChange.value)
const canViewAudits = computed(() =>
  userStore.hasEffectiveRole('common', 'view_compdocimportaudit')
)
const initialFilters = computed(() => {
  const name = typeof route.query.name === 'string' ? route.query.name.trim().slice(0, 256) : ''
  return name ? { name } : {}
})
const popup = ref()
const upload = ref()
const graph = ref()
const download = ref()
const selectedDocument = ref<ICompDoc | null>(null)
const workspaceVisible = ref(false)
const activeDocument = computed(() => {
  const selectedId = selectedDocument.value?.id
  return store.getCompdocs.find((document) => document.id === selectedId) || selectedDocument.value
})
const overrides = useCompdocColumnOverrides()
const table = useCompdocRemoteTable({
  project,
  canView,
  columnOverrides: overrides.columns,
  initialFilters
})
const issueChecks = useCompdocIssueChecks(
  computed(() => store.getCompdocs),
  overrides.issueValues
)
watch(project, closeWorkspace)

function permission(action: string) {
  return computed(() => userStore.hasEffectiveRole(project.value, `${action}_compdoc`))
}

function createDocument() {
  popup.value?.openModal(createEmptyCompdoc(), 'new')
}

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
    // The shared request handler already presents the recoverable API error.
  }
}
</script>

<template>
  <n-alert v-if="!canView" type="warning" :bordered="false">
    You do not have permission to view this project's compliance documents.
  </n-alert>
  <n-alert v-else-if="store.fieldsError" type="error" :bordered="false">
    Table schema could not be loaded: {{ store.fieldsError }}
    <template #action>
      <n-button size="small" @click="table.initialize(project, true)">Retry</n-button>
    </template>
  </n-alert>

  <template v-if="canView">
    <CompDocTableToolbar
      :project="project"
      :can-import="canImport"
      :can-create="canImport"
      :can-delete="canDelete"
      :can-view-audits="canViewAudits"
      :count="store.pagination.count"
      :page-size="table.pageSize.value"
      :checking="issueChecks.checking.value"
      :progress="issueChecks.progress.value"
      @import="upload.setActive(true)"
      @create="createDocument"
      @summary="graph.openModal(store.getCompdocs)"
      @check="issueChecks.checkAll"
      @export="download.openModal('Excel')"
      @settings="table.settings.open"
      @page-size="table.handlePageSize"
    />

    <n-data-table
      :loading="store.isLoading"
      striped
      remote
      size="medium"
      :columns="table.columns.value"
      :data="store.getCompdocs"
      :pagination="table.pagination.value"
      :row-key="table.rowKey"
      :row-props="rowProps"
      :filter-icon-popover-props="table.filterIconPopover"
      @update:filters="table.handleFilters"
      @update:sorter="table.handleSorter"
      @update:page="table.handlePage"
      @update:page-size="table.handlePageSize"
    />
    <n-text depth="3" class="compdoc-table-hint">
      Double-click a document row to open its workspace. Press Enter when a row is focused.
    </n-text>

    <UpdateForm ref="popup" :can-edit="canChange" />
    <CompDocWorkspace
      v-model:show="workspaceVisible"
      :document="activeDocument"
      :project="project"
      :can-edit="canChange"
      :can-delete="canDelete"
      @view="popup?.openModal($event, 'view')"
      @edit="popup?.openModal($event, 'update')"
      @export="download?.openModal('Compliance Document Register')"
      @copy="copyDocumentPath"
      @delete="confirmDocumentDeletion"
    />
    <UploadPopup v-if="canImport" ref="upload" :upload-url="store.getUploadUrl" />
    <GraphComponent ref="graph" />
    <DownloadComponent ref="download" />
    <CompDocColumnSettings
      v-model:show="table.settings.state.visible"
      v-model:settings="table.settings.state.list"
      :fields="store.fields"
      @default="table.settings.useDefault"
      @all="table.settings.useAll"
      @reset="table.settings.reset"
      @apply="table.settings.apply"
    />
  </template>
</template>
