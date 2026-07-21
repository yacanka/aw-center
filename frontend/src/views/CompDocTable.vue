<script setup lang="ts">
import { h, ref, onUnmounted, watch, computed } from 'vue'
import {
  NButton,
  NDataTable,
  NSpace,
  NTag,
  NIcon,
  NSpin,
  NText,
  NSelect,
  DataTableColumns,
  PopoverProps,
  SelectOption,
  PaginationInfo
} from 'naive-ui'
import { useCompdocStore } from '@/stores/compdoc'
import { useDocproofStore } from '@/stores/docproof'
import { useOrgsStore } from '@/stores/organizations'
import UpdateForm from '@/components/compdoc/CompDocPopup.vue'
import UploadPopup from '@/components/compdoc/UploadPopup.vue'
import ImportAuditHistory from '@/components/compdoc/ImportAuditHistory.vue'
import CompDocBulkDelete from '@/components/compdoc/CompDocBulkDelete.vue'
import Details from '@/components/compdoc/DetailedInfo.vue'
import GraphComponent from '@/components/compdoc/Graph.vue'
import DownloadComponent from '@/components/Downloader.vue'
import {
  Settings24Regular,
  ChannelAdd24Regular,
  Add24Regular,
  DataBarVertical24Regular,
  Delete24Regular,
  Eye24Regular,
  Branch24Regular,
  DocumentArrowDown20Regular,
  Document24Regular
} from '@vicons/fluent'
import { useRoute } from 'vue-router'
import { useUserStore } from '@/stores/user'
import { getType } from '@/utils/general'
import { getDateFilterMenuFunc } from '@/components/table/advancedFilterMenus'
import { getStringFilterMenuFunc } from '@/components/table/valueFilterMenus'
import {
  createEmptyCompdoc,
  mocOptions,
  statusColors,
  statusOptions
} from '@/services/compdocCatalog'
import { getArrayFilterFunc, getDateFilterFunc, getStringFilterFunc } from '@/services/tableFilters'
import { IColumnSetting, ICompDoc } from '@/models/compdocs'
import {
  buildCompdocTableQuery,
  collectUniqueTechDocumentNumbers,
  mapWithConcurrencyLimit,
  waitForRetry
} from '@/composables/compdoc/table'
import { useCompdocColumnSettings } from '@/composables/compdoc/columnSettings'

const route = useRoute()
const store = useCompdocStore()
const orgs = useOrgsStore()
const proofStore = useDocproofStore()
const userStore = useUserStore()
const canViewImportAudits = computed(() =>
  userStore.hasEffectiveRole('common', 'view_compdocimportaudit')
)
const projectAppLabel = computed(() => String(route.params.project || ''))
const canView = computed(() => userStore.hasEffectiveRole(projectAppLabel.value, 'view_compdoc'))
const canAdd = computed(() => userStore.hasEffectiveRole(projectAppLabel.value, 'add_compdoc'))
const canChange = computed(() =>
  userStore.hasEffectiveRole(projectAppLabel.value, 'change_compdoc')
)
const canDelete = computed(() =>
  userStore.hasEffectiveRole(projectAppLabel.value, 'delete_compdoc')
)
const canImport = computed(() => canAdd.value && canChange.value)
const canCreate = canImport

const columnSettings = ref({
  visible: false,
  list: [] as IColumnSetting[]
})

const page = ref(1)
const pageSize = ref(parseInt(localStorage.getItem('compdocs>page_size') || '8'))

const pagination = computed<Partial<PaginationInfo>>(() => ({
  page: page.value,
  pageSize: pageSize.value,
  itemCount: store.pagination.count,
  showSizePicker: true,
  pageSizes: [8, 25, 50, 100]
}))

const filterValue = ref<Record<string, any>>({})
const techIssueList = ref<Record<string, any>>({})
const coverPageIssueList = ref<Record<string, any>>({})
let currentColumns = ref<DataTableColumns<ICompDoc>>([])
const checkIssuesButton = ref({
  disabled: false
})
const issueCheckProgress = ref({
  completed: 0,
  total: 0
})

const ISSUE_CHECK_CONCURRENCY_LIMIT = 4
const ISSUE_CHECK_RETRY_LIMIT = 1
const ISSUE_CHECK_RETRY_DELAY_MS = 600
const columnSelections: SelectOption[] = []

const popupComponent = ref()
const uploadPopup = ref()
const table = ref()
const graphComponent = ref()
const downloadComponent = ref()

const filterIconPopover: PopoverProps = {
  trigger: 'click',
  duration: 250,
  displayDirective: 'show'
}

const onFilter = (attrib: string, filterData: any) => {
  filterValue.value[attrib] = filterData
  page.value = 1
  fetchCompdocs()
}

const onClean = (attrib: string) => {
  filterValue.value[attrib] = null
  page.value = 1
  fetchCompdocs()
}

const columns = ref<DataTableColumns<ICompDoc>>([
  {
    type: 'expand',
    width: 2,
    expandable: (row) => true,
    renderExpand: (row) => {
      return h(Details, { compdoc: row })
    }
  },
  {
    title: 'Panel',
    key: 'panel',
    width: 15,
    sorter: 'default',
    filterOptions: [],
    filter: getArrayFilterFunc('panel') as any,
    ellipsis: {
      tooltip: true
    }
  },
  {
    title: 'Ata',
    key: 'ata',
    width: 10,
    sorter: 'default',
    filterOptions: []
  },
  {
    title: 'Name',
    key: 'name',
    width: 15,
    sorter: 'default',
    filterMultiple: false,
    renderFilterMenu: getStringFilterMenuFunc('name', filterValue, onFilter),
    //defaultSortOrder: 'ascend',
    ellipsis: {
      tooltip: true
    }
  },
  {
    title: 'Cover Page No',
    key: 'cover_page_no',
    filter: getStringFilterFunc('cover_page_no'),
    width: 13
  },
  {
    title: 'Cover Page Issue',
    key: 'cover_page_issue',
    align: 'center',
    width: 15,
    render(row) {
      const coverPageNumber = String(row.cover_page_no || '')
      const issueNo = coverPageIssueList.value[coverPageNumber]
      if (issueNo === undefined) {
        return h(
          NText,
          {
            title: 'Double Click',
            style: { userSelect: 'text', cursor: 'pointer' },
            class: 'cell-color',
            onMouseenter: (e: MouseEvent) => {
              ;(e.currentTarget as HTMLElement).classList.add('hovered')
            },
            onMouseleave: (e: MouseEvent) => {
              ;(e.currentTarget as HTMLElement).classList.remove('hovered')
            },
            onDblclick: () => {
              coverPageIssueList.value[coverPageNumber] = null
              proofStore
                .search(coverPageNumber)
                .then((res) => {
                  coverPageIssueList.value[coverPageNumber] = res
                })
                .catch(() => {
                  coverPageIssueList.value[coverPageNumber] = undefined
                })
            }
          },
          { default: () => row.cover_page_issue }
        )
      } else if (issueNo === null) {
        return h(NSpin, { size: 22 }, { default: () => 'Loading' })
      } else {
        return h(
          NTag,
          { type: issueNo == row.cover_page_issue ? 'success' : 'warning', size: 'small' },
          { default: () => issueNo }
        )
      }
    },
    ellipsis: {
      tooltip: true
    }
  },
  {
    title: 'Tech Doc No',
    key: 'tech_doc_no',
    width: 16,
    ellipsis: {
      tooltip: true
    },
    render(row) {
      const body: any = []

      if (row.tech_doc_no) {
        body[0] = h(NText, {}, { default: () => row.tech_doc_no })
      }

      if (row.tech_doc_no_2) {
        body[1] = h(NText, {}, { default: () => row.tech_doc_no_2 })
      }

      return h(NSpace, {}, { default: () => body })
    }
  },
  {
    title: 'Tech Doc Issue',
    key: 'tech_doc_issue',
    align: 'center',
    filter: getStringFilterFunc('tech_doc_issue'),
    width: 12,
    ellipsis: {
      tooltip: true
    },
    render(row) {
      const body: any = []
      if (row.tech_doc_no) {
        const techDocumentNumber = String(row.tech_doc_no)
        const issueNo1 = techIssueList.value[techDocumentNumber]
        if (issueNo1 === undefined) {
          body[0] = h(
            NText,
            {
              title: 'Double Click',
              style: { userSelect: 'text', cursor: 'pointer' },
              class: 'cell-color',
              onMouseenter: (e: MouseEvent) => {
                ;(e.currentTarget as HTMLElement).classList.add('hovered')
              },
              onMouseleave: (e: MouseEvent) => {
                ;(e.currentTarget as HTMLElement).classList.remove('hovered')
              },
              onDblclick: () => {
                techIssueList.value[techDocumentNumber] = null
                proofStore
                  .search(techDocumentNumber)
                  .then((res) => {
                    techIssueList.value[techDocumentNumber] = res
                  })
                  .catch(() => {
                    techIssueList.value[techDocumentNumber] = undefined
                  })
              }
            },
            { default: () => row.tech_doc_issue }
          )
        } else if (issueNo1 === null) {
          body[0] = h(NSpin, { size: 22 }, { default: () => 'Loading' })
        } else {
          body[0] = h(
            NTag,
            { type: issueNo1 == row.tech_doc_issue ? 'success' : 'warning', size: 'small' },
            { default: () => issueNo1 }
          )
        }
      } else {
        body[0] = row.tech_doc_issue
      }

      if (row.tech_doc_no_2) {
        const secondTechDocumentNumber = String(row.tech_doc_no_2)
        const issueNo2 = techIssueList.value[secondTechDocumentNumber]
        if (issueNo2 === undefined) {
          body[1] = h(
            NText,
            {
              title: 'Double Click',
              style: { userSelect: 'text', cursor: 'pointer' },
              class: 'cell-color',
              onMouseenter: (e: MouseEvent) => {
                ;(e.currentTarget as HTMLElement).classList.add('hovered')
              },
              onMouseleave: (e: MouseEvent) => {
                ;(e.currentTarget as HTMLElement).classList.remove('hovered')
              },
              onDblclick: () => {
                techIssueList.value[secondTechDocumentNumber] = null
                proofStore
                  .search(secondTechDocumentNumber)
                  .then((res) => {
                    techIssueList.value[secondTechDocumentNumber] = res
                  })
                  .catch(() => {
                    techIssueList.value[secondTechDocumentNumber] = undefined
                  })
              }
            },
            { default: () => row.tech_doc_issue_2 }
          )
        } else if (issueNo2 === null) {
          body[1] = h(NSpin, { size: 22 }, { default: () => 'Loading' })
        } else {
          body[1] = h(
            NTag,
            { type: issueNo2 == row.tech_doc_issue_2 ? 'success' : 'warning', size: 'small' },
            { default: () => issueNo2 }
          )
        }
      } else {
        body[1] = row.tech_doc_issue_2
      }

      return h(NSpace, { vertical: true }, { default: () => body })
    }
  },
  {
    title: 'UBM Target Date',
    key: 'ubm_target_date',
    filter: getDateFilterFunc('ubm_target_date') as any,
    renderFilterMenu: getDateFilterMenuFunc('ubm_target_date', onFilter, onClean),
    width: 13
  },
  {
    title: 'UBM Delivery Date',
    key: 'ubm_delivery_date',
    filter: getDateFilterFunc('ubm_delivery_date') as any,
    renderFilterMenu: getDateFilterMenuFunc('ubm_delivery_date', onFilter, onClean),
    width: 13
  },
  {
    title: 'MoC',
    key: 'moc',
    filterOptions: mocOptions,
    width: 10
  },
  {
    title: 'Status',
    key: 'status',
    width: 15,
    sorter: 'default',
    filterOptions: statusOptions,
    //renderFilterMenu: getArrayFilterMenuFunc("status", onFilter, onClean),
    filter: getArrayFilterFunc('status') as any,
    render(row) {
      return h(
        NTag,
        {
          color: {
            color: statusColors[String(row.status)]?.color25,
            textColor: statusColors[String(row.status)]?.color
          },
          bordered: false
        },
        {
          default: () => {
            if (row.status) {
              const status = String(row.status) == 'delayed' ? 'to_be_issued' : String(row.status)
              return status.charAt(0).toUpperCase() + status.slice(1).replaceAll('_', ' ')
            }
          }
        }
      )
    }
  },
  {
    title: 'Actions',
    key: 'actions',
    width: 20,
    render(row) {
      return h(
        NSpace,
        {},
        {
          default: () => [
            h(
              NButton,
              {
                ghost: true,
                size: 'small',
                type: 'info',
                focusable: false,
                renderIcon: () => h(Eye24Regular),
                onClick: () => {
                  popupComponent.value.openModal(row, 'view')
                }
              },
              { default: () => null }
            ),
            h(
              NButton,
              {
                ghost: true,
                size: 'small',
                type: 'warning',
                focusable: false,
                renderIcon: () => h(Document24Regular),
                onClick: () => {
                  downloadComponent.value.openModal('Cover Page')
                  //store.createCoverPage(row)
                }
              },
              { default: () => null }
            ),
            canDelete.value
              ? h(
                  NButton,
                  {
                    ghost: true,
                    size: 'small',
                    type: 'error',
                    focusable: false,
                    renderIcon: () => h(Delete24Regular),
                    onClick: () => {
                      window.$dialog.error({
                        title: 'Delete',
                        content: 'Are you sure to delete?',
                        positiveText: 'Yes',
                        negativeText: 'No',
                        onPositiveClick: () => {
                          if (row.id) store.deleteCompdoc(row.id)
                        }
                      })
                    }
                  },
                  { default: () => null }
                )
              : null
          ]
        }
      )
    }
  }
])

const columnSettingsManager = useCompdocColumnSettings({
  allColumns: columns,
  currentColumns,
  columnSelections,
  filterValue,
  onFilter,
  onClean
})
columnSettings.value = columnSettingsManager.state

watch(
  () => [route.params.project, canView.value] as const,
  ([new_value, hasViewPermission]) => {
    store.setProjectName(new_value as string)
    page.value = 1
    if (!hasViewPermission) {
      store.clearList()
      return
    }
    fetchCompdocs()

    orgs.setProject(new_value as string)
    orgs.fetchPanels().then(() => {
      const panelIndex = columns.value.findIndex((item: any) => item.key == 'panel')
      if (panelIndex !== -1) {
        columns.value[panelIndex].filterOptions = orgs.getPanelOptions as any
      }

      const ataIndex = columns.value.findIndex((item: any) => item.key == 'ata')
      if (ataIndex !== -1) {
        columns.value[ataIndex].filterOptions = orgs.getAtaOptions as any
      }
    })
    refreshColumnSelections().then(() => {
      loadColumnSettings()
      applyColumnSettings()
    })
  },
  { immediate: true }
)

function buildCompdocQuery() {
  return buildCompdocTableQuery(filterValue.value, {
    page: page.value,
    pageSize: pageSize.value
  })
}

function fetchCompdocs() {
  if (!canView.value) return Promise.resolve()
  return store.fetchCompdocs(buildCompdocQuery())
}

function handlePageUpdate(newPage: number) {
  page.value = newPage
  fetchCompdocs()
}

function handleTablePageSizeUpdate(newPageSize: number) {
  pageSize.value = newPageSize
  page.value = 1
  localStorage.setItem('compdocs>page_size', newPageSize.toString())
  fetchCompdocs()
}

function showpUploadForm() {
  uploadPopup.value.setActive(true)
}

function rowKey(row: ICompDoc) {
  return row.id || ''
}

function showAddCompDocForm(mode: string) {
  popupComponent.value.openModal(createEmptyCompdoc(), mode)
}

const getFilteredTable = () => {
  if (!table.value?.data) {
    return []
  }
  const filteredTable = table.value.data.filter((compdoc: ICompDoc) => {
    for (const key in filterValue.value) {
      if (filterValue.value[key] && key.includes('date')) {
        const dateFilterFunc = getDateFilterFunc(key)
        if (!dateFilterFunc(filterValue.value[key], compdoc)) {
          return false
        }
      } else if (filterValue.value[key] && getType(filterValue.value[key]) == 'array') {
        const arrayFilterFunc = getArrayFilterFunc(key)
        if (!arrayFilterFunc(filterValue.value[key], compdoc)) {
          return false
        }
      } else if (filterValue.value[key] && getType(filterValue.value[key]) == 'string') {
        const stringFilterFunc = getStringFilterFunc(key)
        if (!stringFilterFunc(filterValue.value[key], compdoc)) {
          return false
        }
      }
    }
    return true
  })
  return filteredTable
}

function showAnalyzeBar() {
  graphComponent.value.openModal(getFilteredTable())
}

function exportExcel() {
  downloadComponent.value.openModal('Excel')
}

async function searchIssueWithRetry(docNo: string) {
  for (let attempt = 0; attempt <= ISSUE_CHECK_RETRY_LIMIT; attempt++) {
    try {
      return await proofStore.search(docNo)
    } catch (error) {
      if (attempt === ISSUE_CHECK_RETRY_LIMIT) throw error
      await waitForRetry(ISSUE_CHECK_RETRY_DELAY_MS * (attempt + 1))
    }
  }
}

async function checkSingleIssue(docNo: string) {
  techIssueList.value[docNo] = null

  try {
    techIssueList.value[docNo] = await searchIssueWithRetry(docNo)
    return { success: true }
  } catch (error) {
    techIssueList.value[docNo] = undefined
    return { success: false }
  } finally {
    issueCheckProgress.value.completed += 1
  }
}

async function checkAllIssues() {
  checkIssuesButton.value.disabled = true
  const documentNumbers = collectUniqueTechDocumentNumbers(getFilteredTable())
  issueCheckProgress.value = { completed: 0, total: documentNumbers.length }

  try {
    const results = await mapWithConcurrencyLimit(
      documentNumbers,
      ISSUE_CHECK_CONCURRENCY_LIMIT,
      checkSingleIssue
    )
    const successCount = results.filter((result) => result.success).length
    const failCount = results.length - successCount
    window.$message.info(
      `Checking the issues is over! Success: ${successCount}, Fail: ${failCount}`
    )
  } finally {
    checkIssuesButton.value.disabled = false
  }
}

function handlePageSizeInput(number: number) {
  if (number) {
    handleTablePageSizeUpdate(number)
  }
}

async function openColumnSettings() {
  columnSettingsManager.open()
  await refreshColumnSelections()
}

async function refreshColumnSelections() {
  await store.fetchCompDocFields()
  columnSelections.splice(0, columnSelections.length, ...store.getCompdocFields)
}

function handleFieldChange() {
  columnSettingsManager.handleFieldChange()
}

function applyColumnSettings() {
  columnSettingsManager.apply()
}

function resetColumnSettings() {
  columnSettingsManager.reset()
}

function handleFilterChange(filters: Record<string, unknown>) {
  for (let filter in filters) {
    filterValue.value[filter] = filters[filter]
  }
  page.value = 1
  fetchCompdocs()
}

function loadColumnSettings() {
  columnSettingsManager.load()
}

onUnmounted(() => {
  store.clearList()
})
</script>

<template>
  <n-alert v-if="!canView" type="warning" :bordered="false">
    You do not have permission to view this project's compliance documents.
  </n-alert>
  <n-space v-if="canView" justify="space-between">
    <n-space>
      <n-button v-if="canImport" @click="showpUploadForm" :focusable="false">
        <template #icon>
          <n-icon size="24">
            <ChannelAdd24Regular />
          </n-icon>
        </template>
        Import
      </n-button>
      <ImportAuditHistory
        :allowed="canViewImportAudits"
        :project="String(route.params.project || '')"
      />
      <n-button v-if="canCreate" @click="showAddCompDocForm('new')" :focusable="false">
        <template #icon>
          <n-icon size="24">
            <Add24Regular />
          </n-icon>
        </template>
        New
      </n-button>
      <n-button @click="showAnalyzeBar" :focusable="false">
        <template #icon>
          <n-icon size="24">
            <DataBarVertical24Regular />
          </n-icon>
        </template>
        Summary
      </n-button>
      <n-button
        @click="checkAllIssues"
        :focusable="false"
        :loading="checkIssuesButton.disabled"
        :disabled="checkIssuesButton.disabled"
      >
        <template #icon>
          <n-icon size="24">
            <Branch24Regular />
          </n-icon>
        </template>
        Check Issues
      </n-button>
      <n-text v-if="checkIssuesButton.disabled || issueCheckProgress.total > 0" depth="3">
        Checked {{ issueCheckProgress.completed }}/{{ issueCheckProgress.total }}
      </n-text>
    </n-space>
    <n-space>
      <n-button ghost color="#65B25D" @click="exportExcel" :focusable="false">
        <template #icon>
          <n-icon size="24">
            <DocumentArrowDown20Regular />
          </n-icon>
        </template>
        Export Excel
      </n-button>
      <CompDocBulkDelete
        v-if="canDelete"
        :project="projectAppLabel"
        :count="store.pagination.count"
      />
    </n-space>
  </n-space>

  <n-flex v-if="canView" justify="end" style="margin: 16px 0 4px 0">
    <n-space>
      <strong>Page Size: </strong>
      <n-input-number
        :value="pageSize"
        size="tiny"
        placeholder="Value"
        style="width: 50px"
        :show-button="false"
        @update:value="handlePageSizeInput"
      />
    </n-space>
    <n-text> <strong>Total: </strong>{{ store.pagination.count }} </n-text>
    <n-button size="tiny" @click="openColumnSettings" :focusable="false">
      <template #icon>
        <Settings24Regular />
      </template>
    </n-button>
  </n-flex>

  <n-data-table
    v-if="canView"
    ref="table"
    :loading="store.isLoading"
    striped
    :columns="currentColumns"
    :data="store.getCompdocs"
    remote
    :pagination="pagination"
    :row-key="rowKey"
    @update:filters="handleFilterChange"
    @update:page="handlePageUpdate"
    @update:page-size="handleTablePageSizeUpdate"
    :filterIconPopoverProps="filterIconPopover"
    size="medium"
  />

  <UpdateForm v-if="canView" ref="popupComponent" :can-edit="canChange" />
  <UploadPopup v-if="canImport" ref="uploadPopup" :uploadUrl="store.getUploadUrl" />
  <GraphComponent v-if="canView" ref="graphComponent" />
  <DownloadComponent v-if="canView" ref="downloadComponent" />

  <n-modal
    v-if="canView"
    v-model:show="columnSettings.visible"
    preset="card"
    title="Column Settings"
    :style="{ width: '800px' }"
    :mask-closable="true"
  >
    <n-scrollbar style="max-height: 600px; padding-right: 16px">
      <n-dynamic-input
        v-model:value="columnSettings.list"
        show-sort-button
        :min="1"
        @create="
          () => {
            return { key: null }
          }
        "
      >
        <template #default="{ value }">
          <n-grid cols="32" x-gap="16">
            <n-grid-item span="12">
              <n-select
                v-model:value="value.key"
                :options="columnSelections"
                placeholder="Select Column"
                @update:value="handleFieldChange"
              />
            </n-grid-item>
            <n-grid-item span="6">
              <n-input-number v-model:value="value.width" placeholder="Width" :min="1" />
            </n-grid-item>
            <n-grid-item span="4" v-if="value.key != 'actions'">
              <n-button
                v-model:value="value.sorter"
                :type="value.sorter ? 'success' : 'default'"
                :focusable="false"
                :style="{ width: '64px' }"
                @click="
                  () => {
                    value.sorter = value.sorter ? false : true
                  }
                "
              >
                Sorter
              </n-button>
            </n-grid-item>
            <n-grid-item span="4" v-if="value.key != 'actions'">
              <n-button
                v-model:value="value.filter"
                :type="value.filter ? 'success' : 'default'"
                :focusable="false"
                :style="{ width: '64px' }"
                @click="
                  () => {
                    value.filter = value.filter ? false : true
                  }
                "
              >
                Filter
              </n-button>
            </n-grid-item>
            <n-grid-item span="4" v-if="value.key != 'actions'">
              <n-button
                v-model:value="value.ellipsis"
                :type="value.ellipsis ? 'success' : 'default'"
                :focusable="false"
                :style="{ width: '64px' }"
                @click="
                  () => {
                    value.ellipsis = value.ellipsis ? false : true
                  }
                "
              >
                Ellipsis
              </n-button>
            </n-grid-item>
          </n-grid>
        </template>
      </n-dynamic-input>
    </n-scrollbar>
    <n-flex justify="center" style="margin-top: 10px">
      <n-button type="error" @click="resetColumnSettings">Reset</n-button>
      <n-button type="info" @click="applyColumnSettings">Apply</n-button>
    </n-flex>
  </n-modal>
</template>

<style>
.cell-color {
  color: var(--n-text-color);
}

.cell-color.hovered {
  color: var(--n-th-icon-color-active);
}
</style>
