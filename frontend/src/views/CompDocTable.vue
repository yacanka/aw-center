<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import UpdateForm from '@/components/compdoc/CompDocPopup.vue'
import CompDocWorkspace from '@/components/compdoc/CompDocWorkspace.vue'
import UploadPopup from '@/components/compdoc/UploadPopup.vue'
import CompDocColumnSettings from '@/components/compdoc/CompDocColumnSettings.vue'
import CompDocTableToolbar from '@/components/compdoc/CompDocTableToolbar.vue'
import CompDocBulkActions from '@/components/compdoc/CompDocBulkActions.vue'
import GraphComponent from '@/components/compdoc/Graph.vue'
import DownloadComponent from '@/components/Downloader.vue'
import { useCompdocStore } from '@/stores/compdoc'
import { useUserStore } from '@/stores/user'
import { createEmptyCompdoc } from '@/services/compdocCatalog'
import { compdocQuickFilter, compdocRouteFilters } from '@/services/compdocQuickFilters'
import { useCompdocColumnOverrides } from '@/composables/compdoc/columnOverrides'
import { useCompdocIssueChecks } from '@/composables/compdoc/issueChecks'
import { useCompdocRemoteTable } from '@/composables/compdoc/remoteTable'
import { useCompdocWorkspace } from '@/composables/compdoc/workspace'
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
const initialFilters = computed(() => compdocRouteFilters(route.query))
const popup = ref()
const upload = ref()
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
const overrides = useCompdocColumnOverrides()
const table = useCompdocRemoteTable({
  project,
  canView,
  columnOverrides: overrides.columns,
  initialFilters
})
const checkedRowKeys = ref<Array<string | number>>([])
const selectedDocuments = computed(() => {
  const selected = new Set(checkedRowKeys.value.map(String))
  return store.getCompdocs.filter((document) => document.id && selected.has(document.id))
})
const displayColumns = computed(() => [{ type: 'selection' as const }, ...table.columns.value])
const issueChecks = useCompdocIssueChecks(
  computed(() => store.getCompdocs),
  overrides.issueValues
)
watch(project, closeWorkspace)
watch(
  () => [route.query.document, store.getCompdocs],
  ([document]) => {
    if (typeof document !== 'string' || workspaceVisible.value) return
    const match = store.getCompdocs.find((item) => item.id === document)
    if (match) workspace.openWorkspace(match)
  }
)

function permission(action: string) {
  return computed(() => userStore.hasEffectiveRole(project.value, `${action}_compdoc`))
}

function createDocument() {
  popup.value?.openModal(createEmptyCompdoc(), 'new')
}

function applyQuickFilter(value: string) {
  table.replaceQuickFilters(compdocQuickFilter(value))
}

async function completeBulkAction() {
  checkedRowKeys.value = []
  await table.initialize(project.value, canView.value)
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
      :can-create="canAdd"
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
      @search="table.updateCustomFilter('search', $event)"
      @quick-filter="applyQuickFilter"
    />

    <CompDocBulkActions
      v-if="selectedDocuments.length"
      :project="project"
      :documents="selectedDocuments"
      :can-change="canChange"
      :can-delete="canDelete"
      @completed="completeBulkAction"
    />

    <n-data-table
      :loading="store.isLoading"
      striped
      remote
      size="medium"
      max-height="max(320px, calc(100vh - 300px))"
      :columns="displayColumns"
      :data="store.getCompdocs"
      :pagination="table.pagination.value"
      :row-key="table.rowKey"
      :row-props="rowProps"
      :checked-row-keys="checkedRowKeys"
      :filter-icon-popover-props="table.filterIconPopover"
      @update:filters="table.handleFilters"
      @update:sorter="table.handleSorter"
      @update:page="table.handlePage"
      @update:page-size="table.handlePageSize"
      @update:checked-row-keys="checkedRowKeys = $event"
    />
    <n-text depth="3" class="compdoc-table-hint">
      Double-click a document row to open its workspace. Press Enter or Space when a row is focused.
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
      @changed="table.initialize(project, true)"
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
