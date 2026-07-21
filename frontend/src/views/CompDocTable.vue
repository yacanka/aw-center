<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute } from 'vue-router'
import UpdateForm from '@/components/compdoc/CompDocPopup.vue'
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
const popup = ref()
const upload = ref()
const graph = ref()
const download = ref()
const overrides = useCompdocColumnOverrides({ canDelete, popup, download })
const table = useCompdocRemoteTable({
  project,
  canView,
  columnOverrides: overrides.columns
})
const issueChecks = useCompdocIssueChecks(
  computed(() => store.getCompdocs),
  overrides.issueValues
)

function permission(action: string) {
  return computed(() => userStore.hasEffectiveRole(project.value, `${action}_compdoc`))
}

function createDocument() {
  popup.value.openModal(createEmptyCompdoc(), 'new')
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
      :filter-icon-popover-props="table.filterIconPopover"
      @update:filters="table.handleFilters"
      @update:sorter="table.handleSorter"
      @update:page="table.handlePage"
      @update:page-size="table.handlePageSize"
    />

    <UpdateForm ref="popup" :can-edit="canChange" />
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

<style>
.cell-color {
  color: var(--n-text-color);
}

.cell-color.hovered {
  color: var(--n-th-icon-color-active);
}
</style>
