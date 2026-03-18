<script setup lang="ts">
import { h, ref, onMounted, onUnmounted, watch, nextTick, computed } from 'vue'
import { NButton, NDataTable, NSpace, NTag, NUpload, NIcon, NEllipsis, NTooltip, NSpin, NText, NInput, NFormItem, NForm, NDatePicker, NSelect, DataTableColumns, PopoverTrigger, PopoverInst, PopoverProps, DataTableColumn, SelectOption, PaginationInfo } from 'naive-ui'
import { useCompdocStore, useDocproofStore, useOrgsStore } from '@/stores/api'
import UpdateForm from '@/components/compdoc/CompDocPopup.vue';
import UploadPopup from '@/components/compdoc/UploadPopup.vue';
import Details from '@/components/compdoc/DetailedInfo.vue';
import GraphComponent from '@/components/compdoc/Graph.vue';
import DownloadComponent from '@/components/Downloader.vue';
import { Settings24Regular, ChannelAdd24Regular, Add24Regular, DataBarVertical24Regular, Edit24Regular, Delete24Regular, Eye24Regular, Branch24Regular, DocumentArrowDown20Regular, Document24Regular, ContractDownLeft16Filled } from '@vicons/fluent';
import { useRoute } from 'vue-router'
import { toTitleCase } from '@/utils/text'
import { getType } from '@/utils/general'
import { getDateFilterMenuFunc, getStringFilterMenuFunc, getArrayFilterMenuFunc, getStringFilterFunc, getArrayFilterFunc, getDateFilterFunc, statusOptions, statusColors, mocOptions, createEmpty } from '@/stores/datatable'
import { IColumnSetting, ICompDoc } from '@/models/compdocs';
import { SelectBaseOption } from 'naive-ui/es/select/src/interface';

const route = useRoute()
const store = useCompdocStore()
const orgs = useOrgsStore()
const proofStore = useDocproofStore()

const columnSettings = ref<{ visible: boolean, list: IColumnSetting[] }>({
  visible: false,
  list: []
})

const pagination = ref<Partial<PaginationInfo>>({
  pageSize: parseInt(localStorage.getItem("compdocs>page_size") || "8")
})

const filterValue = ref<Record<string, any>>({});
const techIssueList = ref<Record<string, any>>({})
const coverPageIssueList = ref<Record<string, any>>({})
let currentColumns = ref<DataTableColumns<ICompDoc>>([])
const checkIssuesButton = ref({
  disabled: false
})
const columnSelections: SelectOption[] = store.getCompdocFields

const popupComponent = ref()
const uploadPopup = ref()
const table = ref()
const graphComponent = ref()
const downloadComponent = ref()

const filterIconPopover: PopoverProps = {
  trigger: "click",
  duration: 250,
  displayDirective: "show",
}

const onFilter = (attrib: string, filterData: any) => {
  filterValue.value[attrib] = filterData
  filterAttr()
}

const onClean = (attrib: string) => {
  filterValue.value[attrib] = null
  filterAttr()
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
    filter: getArrayFilterFunc("panel"),
    ellipsis: {
      tooltip: true
    },
  },
  {
    title: 'Ata',
    key: 'ata',
    width: 10,
    sorter: 'default',
    filterOptions: [],
  },
  {
    title: 'Name',
    key: 'name',
    width: 15,
    sorter: 'default',
    filterMultiple: false,
    renderFilterMenu: getStringFilterMenuFunc("name", filterValue, onFilter),
    //defaultSortOrder: 'ascend',
    ellipsis: {
      tooltip: true
    },
  },
  {
    title: 'Cover Page No',
    key: 'cover_page_no',
    filter: getStringFilterFunc("cover_page_no"),
    width: 13,
  },
  {
    title: 'Cover Page Issue',
    key: 'cover_page_issue',
    align: "center",
    width: 15,
    render(row) {
      const issueNo = coverPageIssueList.value[row.cover_page_no]
      if (issueNo === undefined) {
        return h(
          NText,
          {
            title: "Double Click",
            style: { userSelect: "text", cursor: "pointer" },
            class: "cell-color",
            onMouseenter: (e: MouseEvent) => { (e.currentTarget as HTMLElement).classList.add("hovered") },
            onMouseleave: (e: MouseEvent) => { (e.currentTarget as HTMLElement).classList.remove("hovered") },
            onDblclick: () => {
              coverPageIssueList.value[row.cover_page_no] = null
              proofStore.search(row.cover_page_no).then((res) => {
                coverPageIssueList.value[row.cover_page_no] = res
              }).catch(() => {
                coverPageIssueList.value[row.cover_page_no] = undefined
              })
            }
          },
          { default: () => row.cover_page_issue })
      }
      else if (issueNo === null) {
        return h(NSpin, { size: 22 }, { default: () => "Loading" })
      }
      else {
        return h(
          NTag,
          { type: issueNo == row.cover_page_issue ? "success" : "warning", size: "small" },
          { default: () => issueNo })
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
    filter: getStringFilterFunc("tech_doc_issue"),
    width: 12,
    ellipsis: {
      tooltip: true
    },
    render(row) {
      const body: any = []
      if (row.tech_doc_no) {
        const issueNo1 = techIssueList.value[row.tech_doc_no]
        if (issueNo1 === undefined) {
          body[0] = h(
            NText,
            {
              title: "Double Click",
              style: { userSelect: "text", cursor: "pointer" },
              class: "cell-color",
              onMouseenter: (e: MouseEvent) => { (e.currentTarget as HTMLElement).classList.add("hovered") },
              onMouseleave: (e: MouseEvent) => { (e.currentTarget as HTMLElement).classList.remove("hovered") },
              onDblclick: () => {
                techIssueList.value[row.tech_doc_no] = null
                proofStore.search(row.tech_doc_no).then((res) => {
                  techIssueList.value[row.tech_doc_no] = res
                }).catch(() => {
                  techIssueList.value[row.tech_doc_no] = undefined
                })
              }
            },
            { default: () => row.tech_doc_issue })
        }
        else if (issueNo1 === null) {
          body[0] = h(NSpin, { size: 22 }, { default: () => "Loading" })
        }
        else {
          body[0] = h(
            NTag,
            { type: issueNo1 == row.tech_doc_issue ? "success" : "warning", size: "small" },
            { default: () => issueNo1 })
        }
      } else {
        body[0] = row.tech_doc_issue
      }

      if (row.tech_doc_no_2) {
        const issueNo2 = techIssueList.value[row.tech_doc_no_2]
        if (issueNo2 === undefined) {
          body[1] = h(
            NText,
            {
              title: "Double Click",
              style: { userSelect: "text", cursor: "pointer" },
              class: "cell-color",
              onMouseenter: (e: MouseEvent) => { (e.currentTarget as HTMLElement).classList.add("hovered") },
              onMouseleave: (e: MouseEvent) => { (e.currentTarget as HTMLElement).classList.remove("hovered") },
              onDblclick: () => {
                techIssueList.value[row.tech_doc_no_2] = null
                proofStore.search(row.tech_doc_no_2).then((res) => {
                  techIssueList.value[row.tech_doc_no_2] = res
                }).catch(() => {
                  techIssueList.value[row.tech_doc_no_2] = undefined
                })
              }
            },
            { default: () => row.tech_doc_issue_2 })
        }
        else if (issueNo2 === null) {
          body[1] = h(NSpin, { size: 22 }, { default: () => "Loading" })
        } else {
          body[1] = h(
            NTag,
            { type: issueNo2 == row.tech_doc_issue_2 ? "success" : "warning", size: "small" },
            { default: () => issueNo2 })
        }
      }
      else {
        body[1] = row.tech_doc_issue_2
      }

      return h(NSpace, { vertical: true }, { default: () => body })
    }
  },
  {
    title: 'UBM Target Date',
    key: 'ubm_target_date',
    filter: getDateFilterFunc("ubm_target_date"),
    renderFilterMenu: getDateFilterMenuFunc("ubm_target_date", onFilter, onClean),
    width: 13,
  },
  {
    title: 'UBM Delivery Date',
    key: 'ubm_delivery_date',
    filter: getDateFilterFunc("ubm_delivery_date"),
    renderFilterMenu: getDateFilterMenuFunc("ubm_delivery_date", onFilter, onClean),
    width: 13,
  },
  {
    title: 'MoC',
    key: 'moc',
    filterOptions: mocOptions,
    width: 10,
  },
  {
    title: 'Status',
    key: 'status',
    width: 15,
    sorter: 'default',
    filterOptions: statusOptions,
    //renderFilterMenu: getArrayFilterMenuFunc("status", onFilter, onClean),
    filter: getArrayFilterFunc("status"),
    render(row) {
      return h(
        NTag,
        {
          color: { color: statusColors[row.status]?.color25, textColor: statusColors[row.status]?.color },
          bordered: false
        },
        {
          default: () => {
            if (row.status) {
              return (row.status == "delayed" ? "to_be_issued" : row.status).charAt(0).toUpperCase() + (row.status == "delayed" ? "to_be_issued" : row.status).slice(1).replaceAll('_', ' ')
            }
          },
        }
      )
    },
  },
  {
    title: 'Actions',
    key: 'actions',
    width: 20,
    render(row) {
      return h(NSpace, {}, {
        default: () => [
          h(NButton,
            {
              ghost: true,
              size: 'small',
              type: 'info',
              focusable: false,
              renderIcon: () => h(Eye24Regular),
              onClick: () => {
                popupComponent.value.openModal(row, "view")
              },
            },
            { default: () => null }
          ),
          h(NButton,
            {
              ghost: true,
              size: 'small',
              type: 'warning',
              focusable: false,
              renderIcon: () => h(Document24Regular),
              onClick: () => {
                downloadComponent.value.openModal("Cover Page")
                //store.createCoverPage(row)
              },
            },
            { default: () => null }
          ),
          h(NButton,
            {
              ghost: true,
              size: 'small',
              type: 'error',
              focusable: false,
              renderIcon: () => h(Delete24Regular),
              onClick: () => {
                window.$dialog.error({
                  title: "Delete",
                  content: "Are you sure to delete?",
                  positiveText: "Yes",
                  negativeText: "No",
                  onPositiveClick: () => {
                    store.deleteCompdoc(row.id).then(() => {
                      console.log("Request deleted: ", row.name)
                    }).catch((err) => {
                      console.error("Error while deleting ", row.name, ": ", err)
                    })
                  },
                })
              }
            },
            { default: () => null }
          ),
        ]
      })
    }
  }
])

watch(() => route.params.project,
  (new_value, old_value) => {
    store.setProjectName(new_value as string)
    store.fetchCompdocs().then(() => {
      //applyColumnSettings()
    })

    orgs.setProject(new_value as string)
    orgs.fetchPanels().then(() => {
      const panelIndex = columns.value.findIndex((item: any) => item.key == 'panel')
      if (panelIndex !== -1) {
        columns.value[panelIndex].filterOptions = orgs.getPanelOptions
      }

      const ataIndex = columns.value.findIndex((item: any) => item.key == 'ata')
      if (panelIndex !== -1) {
        columns.value[ataIndex].filterOptions = orgs.getAtaOptions
      }
    })
  }, { immediate: true })



function filterAttr() {
  table.value.filter(filterValue.value)
}

function showpUploadForm() {
  uploadPopup.value.setActive(true)
}

function rowKey(row: ICompDoc) {
  return row.id
}

function showAddCompDocForm(mode: string) {
  popupComponent.value.openModal(createEmpty(), mode)
}

const getFilteredTable = () => {
  if (!table.value?.data) {
    return []
  }
  const filteredTable = table.value.data.filter((compdoc: ICompDoc) => {
    for (const key in filterValue.value) {
      if (filterValue.value[key] && key.includes("date")) {
        const dateFilterFunc = getDateFilterFunc(key)
        if (!dateFilterFunc(filterValue.value[key], compdoc)) {
          return false
        }
      }
      else if (filterValue.value[key] && getType(filterValue.value[key]) == "array") {
        const arrayFilterFunc = getArrayFilterFunc(key)
        if (!arrayFilterFunc(filterValue.value[key], compdoc)) {
          return false
        }
      }
      else if (filterValue.value[key] && getType(filterValue.value[key]) == "string") {
        const stringFilterFunc = getStringFilterFunc(key)
        if (!stringFilterFunc(filterValue.value[key], compdoc)) {
          return false
        }
      }
    }
    return true;
  });
  return filteredTable
}

function showAnalyzeBar() {
  graphComponent.value.openModal(getFilteredTable())
}

function exportExcel() {
  downloadComponent.value.openModal("Excel")
}

async function checkAllIssues() {
  checkIssuesButton.value.disabled = true
  const filteredTable = getFilteredTable()

  const promises = []

  for (const row of filteredTable) {
    const docNos = []
    if (row.tech_doc_no) docNos.push(row.tech_doc_no)
    if (row.tech_doc_no_2) docNos.push(row.tech_doc_no_2)

    for (const docNo of docNos) {
      promises.push(
        proofStore.search(docNo)
          .then(res => {
            techIssueList.value[docNo] = res
            return { success: true }
          })
          .catch(err => {
            return { success: false }
          })
      )
    }
  }

  try {
    const results = await Promise.all(promises)

    const successCount = results.filter(r => r.success).length
    const failCount = results.length - successCount

    const messageType =
      window.$message["info"](`Checking the issues is over! Success: ${successCount}, Fail: ${failCount}`)

  } catch (err) {
    console.error("Hata oluştu:", err)
  } finally {
    checkIssuesButton.value.disabled = false
  }
}

function deleteAllCompDocs() {
  window.$dialog.error({
    title: "Delete",
    content: "Are you sure to delete all compliance documents?",
    positiveText: "Yes",
    negativeText: "No",
    onPositiveClick: async () => {
      const res = await store.deleteCompdocs()
      console.log(res)
    },
  })
}

function handlePageSizeInput(number: number) {
  if (number) {
    pagination.value.pageSize = number
    localStorage.setItem("compdocs>page_size", number.toString())
  }
}

function openColumnSettings() {
  handleFieldChange(null, null)
  columnSettings.value.visible = true
}

function handleFieldChange(value: string | null, option: SelectBaseOption | null) {
  for (const option of columnSelections) {
    const locked = columnSettings.value.list.some((item) => item.key == option.value)
    option.disabled = locked
  }
}

function applyColumnSettings() {
  currentColumns.value = []
  for (let column of columnSettings.value.list) {
    const targetCol: any = columns.value.find((col: any) => {
      return col.key == column.key
    })

    if (targetCol) {
      if (column.sorter != null) {
        targetCol.sorter = column.sorter ? 'default' : null
      }

      if (column.ellipsis != null) {
        targetCol.ellipsis = column.ellipsis ? { tooltip: true } : null
      }

      if (column.filter != null) {
        if (targetCol.filter == null) {
          targetCol.filter = column.filter ? (column.key?.includes("date") ? getDateFilterFunc(column.key) : getStringFilterFunc(column.key)) : null
        }

        if (!targetCol.renderFilterMenu && !targetCol.filterOptions) {
          targetCol.renderFilterMenu = getStringFilterMenuFunc(column.key, filterValue, onFilter)
        }
      }

      if (column.width != null) {
        targetCol.width = column.width
      }
      currentColumns.value.push(targetCol)
    }
    else {
      currentColumns.value.push({
        title: toTitleCase(column.key?.replaceAll("_", " ")),
        key: column.key,
        sorter: column.sorter ? 'default' : null,
        width: column.width ? column.width : 2,
        renderFilterMenu: column.filter ? (column.key?.includes("date") ? getDateFilterMenuFunc(column.key, onFilter, onClean) : getStringFilterMenuFunc(column.key, filterValue, onFilter)) : null,
        filter: column.filter ? (column.key?.includes("date") ? getDateFilterFunc(column.key) : getStringFilterFunc(column.key)) : null,
        ellipsis: column.ellipsis ? { tooltip: true } : null,
      })
    }
  }
  localStorage.setItem("compdocs>column_settings", JSON.stringify(columnSettings.value.list))
}

function resetColumnSettings() {
  localStorage.removeItem("compdocs>column_settings")
  loadColumnSettings()
}

function handleFilterChange(filters: any) {
  for (let filter in filters) {
    filterValue.value[filter] = filters[filter]
  }
}

function loadColumnSettings() {
  const savedColumnSettingsRaw = localStorage.getItem("compdocs>column_settings")
  const savedColumnSettings = (savedColumnSettingsRaw ? JSON.parse(savedColumnSettingsRaw) : null);

  if (savedColumnSettings) {
    columnSettings.value.list = savedColumnSettings
  }
  else {
    columnSettings.value.list = columns.value.map((column: any) => {
      return { key: column.key, width: column.width, sorter: column.sorter ? true : false, filter: column.filter ? true : false, ellipsis: column.ellipsis ? true : false }
    })
  }
}

onMounted(() => {
  loadColumnSettings()
  applyColumnSettings()
})

onUnmounted(() => {
  store.clearList()
})
</script>

<template>
  <n-space justify="space-between">
    <n-space>
      <n-button @click="showpUploadForm" :focusable="false">
        <template #icon>
          <n-icon size=24>
            <ChannelAdd24Regular />
          </n-icon>
        </template>
        Import
      </n-button>
      <n-button @click="showAddCompDocForm('new')" :focusable="false">
        <template #icon>
          <n-icon size=24>
            <Add24Regular />
          </n-icon>
        </template>
        New
      </n-button>
      <n-button @click="showAnalyzeBar" :focusable="false">
        <template #icon>
          <n-icon size=24>
            <DataBarVertical24Regular />
          </n-icon>
        </template>
        Summary
      </n-button>
      <n-button @click="checkAllIssues" :focusable="false" :loading="checkIssuesButton.disabled"
        :disabled="checkIssuesButton.disabled">
        <template #icon>
          <n-icon size=24>
            <Branch24Regular />
          </n-icon>
        </template>
        Check Issues
      </n-button>
    </n-space>
    <n-space>
      <n-button ghost color="#65B25D" @click="exportExcel" :focusable="false">
        <template #icon>
          <n-icon size=24>
            <DocumentArrowDown20Regular />
          </n-icon>
        </template>
        Export Excel
      </n-button>
      <n-button ghost type="error" @click="deleteAllCompDocs" :focusable="false">
        <template #icon>
          <n-icon size=24>
            <Delete24Regular />
          </n-icon>
        </template>
        Delete All
      </n-button>
    </n-space>
  </n-space>

  <n-flex justify="end" style="margin: 16px 0 4px 0">
    <n-space>
      <strong>Page Size: </strong>
      <n-input-number :value="pagination.pageSize" size="tiny" placeholder="Value" style="width: 50px"
        :show-button="false" @update:value="handlePageSizeInput" />
    </n-space>
    <n-text>
      <strong>Total: </strong>{{ getFilteredTable().length }}
    </n-text>
    <n-button size="tiny" @click="openColumnSettings" :focusable="false">
      <template #icon>
        <Settings24Regular />
      </template>
    </n-button>
  </n-flex>

  <n-data-table ref="table" :loading="store.isLoading" striped :columns="currentColumns" :data="store.getCompdocs"
    :pagination="pagination" :row-key="rowKey" @update:filters="handleFilterChange"
    :filterIconPopoverProps="filterIconPopover" size="medium" />

  <UpdateForm ref="popupComponent" />
  <UploadPopup ref="uploadPopup" :uploadUrl="store.getUploadUrl" />
  <GraphComponent ref="graphComponent" />
  <DownloadComponent ref="downloadComponent" />

  <n-modal v-model:show="columnSettings.visible" preset="card" title="Column Settings" :style="{ width: '800px' }"
    :mask-closable="true">
    <n-scrollbar style="max-height: 600px; padding-right: 16px">
      <n-dynamic-input v-model:value="columnSettings.list" show-sort-button :min="1"
        @create="() => { return { key: null } }">
        <template #default="{ value }">
          <n-grid cols=32 x-gap=16>
            <n-grid-item span=12>
              <n-select v-model:value="value.key" :options="columnSelections" placeholder="Select Column"
                @update:value="handleFieldChange" />
            </n-grid-item>
            <n-grid-item span=6>
              <n-input-number v-model:value="value.width" placeholder="Width" :min="1" />
            </n-grid-item>
            <n-grid-item span=4 v-if="value.key != 'actions'">
              <n-button v-model:value="value.sorter" :type="value.sorter ? 'success' : 'default'" :focusable="false"
                :style="{ width: '64px' }" @click="() => { value.sorter = value.sorter ? false : true }">
                Sorter
              </n-button>
            </n-grid-item>
            <n-grid-item span=4 v-if="value.key != 'actions'">
              <n-button v-model:value="value.filter" :type="value.filter ? 'success' : 'default'" :focusable="false"
                :style="{ width: '64px' }" @click="() => { value.filter = value.filter ? false : true }">
                Filter
              </n-button>
            </n-grid-item>
            <n-grid-item span=4 v-if="value.key != 'actions'">
              <n-button v-model:value="value.ellipsis" :type="value.ellipsis ? 'success' : 'default'" :focusable="false"
                :style="{ width: '64px' }" @click="() => { value.ellipsis = value.ellipsis ? false : true }">
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