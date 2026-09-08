<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import UpdateForm from '@/features/compliance/components/CompDocPopup.vue'
import CompDocWorkspace from '@/features/compliance/components/CompDocWorkspace.vue'
import UploadPopup from '@/features/compliance/components/UploadPopup.vue'
import DoorsImportPopup from '@/features/compliance/components/DoorsImportPopup.vue'
import CompDocColumnSettings from '@/features/compliance/components/CompDocColumnSettings.vue'
import CompDocTableToolbar from '@/features/compliance/components/CompDocTableToolbar.vue'
import GraphComponent from '@/features/compliance/components/Graph.vue'
import DownloadComponent from '@/features/compliance/components/Downloader.vue'
import { provideCompdocController } from '@/features/compliance/composables/compdocController'
import { useProjectCatalogStore } from '@/features/projects/stores/projectCatalog'
import { createEmptyCompdoc } from '@/features/compliance/api/compdocCatalog'
import {
  compdocQuickFilter,
  compdocRouteFilters
} from '@/features/compliance/api/compdocQuickFilters'
import { useCompdocColumnOverrides } from '@/features/compliance/composables/columnOverrides'
import { useCompdocIssueChecks } from '@/features/compliance/composables/issueChecks'
import { useCompdocRemoteTable } from '@/features/compliance/composables/remoteTable'
import { useCompdocWorkspace } from '@/features/compliance/composables/workspace'
import { formatApiError } from '@/shared/api/apiError'
import './CompDocTable.css'

const route = useRoute()
const store = provideCompdocController()
const projectCatalog = useProjectCatalogStore()
const project = computed(() => String(route.params.project || ''))
const canView = permission('viewer')
const canAdd = permission('editor')
const canChange = permission('editor')
const canDelete = permission('manager')
const canImport = computed(() => canAdd.value && canChange.value)
const canViewAudits = canView
const catalogReady = computed(() => projectCatalog.status === 'ready')
const initialFilters = computed(() => compdocRouteFilters(route.query))
const workspaceTab = computed(() => {
  const requested = String(route.query.workspace || '')
  if (requested === 'transition' && !canChange.value) return 'overview'
  return ['tracking', 'ownership', 'reviews', 'transition', 'activity'].includes(requested)
    ? (requested as 'tracking' | 'ownership' | 'reviews' | 'transition' | 'activity')
    : 'overview'
})
const popup = ref()
const upload = ref()
const doorsImport = ref()
const graph = ref()
const download = ref()
const workspace = useCompdocWorkspace(store)
const {
  activeDocument,
  closeWorkspace,
  confirmDocumentDeletion,
  copyDocumentPath,
  rowProps,
  workspaceVisible
} = workspace
const overrides = useCompdocColumnOverrides(store)
const table = useCompdocRemoteTable({
  project,
  canView,
  columnOverrides: overrides.columns,
  initialFilters,
  store
})
const displayColumns = computed(() => table.columns.value)
const tableScrollX = computed(() =>
  displayColumns.value.reduce((total, column) => {
    const width = 'width' in column ? Number(column.width) : 0
    const minWidth = 'minWidth' in column ? Number(column.minWidth) : 0
    return total + (Number.isFinite(width) && width > 0 ? width : minWidth || 160)
  }, 0)
)
const issueChecks = useCompdocIssueChecks(
  computed(() => store.getCompdocs),
  overrides.issueValues
)
let linkedDocumentRequest = 0
let workspaceRefreshRequest = 0
watch(project, closeWorkspace)
watch(
  () => [route.query.document, project.value, canView.value, store.getProjectName] as const,
  async ([document, selectedProject, hasAccess, loadedProject]) => {
    const requestId = ++linkedDocumentRequest
    if (
      typeof document !== 'string' ||
      !hasAccess ||
      loadedProject !== selectedProject ||
      workspaceVisible.value
    )
      return
    const match = store.getCompdocs.find((item) => item.id === document)
    if (match) {
      workspace.openWorkspace(match)
      return
    }
    try {
      const fetched = await store.fetchCompdoc(document)
      if (
        requestId === linkedDocumentRequest &&
        route.query.document === document &&
        project.value === selectedProject &&
        !workspaceVisible.value
      ) {
        workspace.openWorkspace(fetched)
      }
    } catch (error) {
      if (requestId === linkedDocumentRequest) window.$message.error(formatApiError(error))
    }
  },
  { immediate: true }
)

function permission(minimum: 'viewer' | 'editor' | 'manager') {
  return computed(() => projectCatalog.hasManagementRole(project.value, 'compliance', minimum))
}

function createDocument() {
  popup.value?.openModal(createEmptyCompdoc(), 'new')
}

function applyQuickFilter(value: string) {
  table.replaceQuickFilters(compdocQuickFilter(value))
}

async function refreshWorkspaceDocument() {
  const requestId = ++workspaceRefreshRequest
  const documentId = activeDocument.value?.id
  const selectedProject = project.value
  await store.fetchCompdocs()
  if (
    !documentId ||
    !workspaceVisible.value ||
    requestId !== workspaceRefreshRequest ||
    project.value !== selectedProject
  )
    return
  try {
    const refreshed = await store.fetchCompdoc(documentId)
    if (
      requestId === workspaceRefreshRequest &&
      workspaceVisible.value &&
      project.value === selectedProject
    ) {
      workspace.openWorkspace(refreshed)
    }
  } catch (error) {
    if (requestId === workspaceRefreshRequest) window.$message.error(formatApiError(error))
  }
}

void projectCatalog.load().catch(() => undefined)
</script>

<template>
  <n-spin v-if="projectCatalog.status === 'loading'" size="small" />
  <n-alert v-else-if="projectCatalog.error" type="error" :bordered="false">
    Project access could not be loaded: {{ projectCatalog.error }}
  </n-alert>
  <n-alert v-else-if="catalogReady && !canView" type="warning" :bordered="false">
    You do not have permission to view this project's compliance documents.
  </n-alert>
  <n-alert v-else-if="store.fieldsError" type="error" :bordered="false">
    Table schema could not be loaded: {{ store.fieldsError }}
    <template #action>
      <n-button size="small" @click="table.initialize(project, true)">Retry</n-button>
    </template>
  </n-alert>

  <template v-if="catalogReady && canView">
    <CompDocTableToolbar
      :project="project"
      :can-import="canImport"
      :can-create="canAdd"
      :can-delete="canDelete"
      :can-view-audits="canViewAudits"
      :count="store.pagination.count"
      :page-size="table.pageSize.value"
      :checking="issueChecks.checking.value"
      :progress="issueChecks.progress.value"
      @import="upload.setActive(true)"
      @import-doors="doorsImport.setActive(true)"
      @create="createDocument"
      @summary="graph.openModal(store.getCompdocs)"
      @check="issueChecks.checkAll"
      @export="download.openModal('Excel')"
      @settings="table.settings.open"
      @page-size="table.handlePageSize"
      @search="table.updateCustomFilter('search', $event)"
      @quick-filter="applyQuickFilter"
    />

    <n-data-table
      :loading="store.isLoading"
      striped
      remote
      size="medium"
      max-height="max(320px, calc(100vh - 300px))"
      :columns="displayColumns"
      :data="store.getCompdocs"
      :scroll-x="tableScrollX"
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
      Double-click a document row to open its workspace. Press Enter or Space when a row is focused.
    </n-text>

    <UpdateForm ref="popup" :can-edit="canChange" />
    <CompDocWorkspace
      v-model:show="workspaceVisible"
      :document="activeDocument"
      :project="project"
      :can-edit="canChange && !activeDocument?.is_archived"
      :can-delete="canDelete"
      :initial-tab="workspaceTab"
      @view="popup?.openModal($event, 'view')"
      @edit="popup?.openModal($event, 'update')"
      @export="download?.openModal('Compliance Document Register')"
      @copy="copyDocumentPath"
      @delete="confirmDocumentDeletion"
      @changed="refreshWorkspaceDocument"
    />
    <UploadPopup v-if="canImport" ref="upload" :upload-url="store.getUploadUrl" />
    <DoorsImportPopup v-if="canImport" ref="doorsImport" :collection-path="store.getUploadUrl" />
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
