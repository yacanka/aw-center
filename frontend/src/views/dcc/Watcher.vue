<script setup lang="ts">
import { h, ref, onMounted } from 'vue'
import axios from 'axios'
import { NButton, NDataTable, NSpace, NTag, NSpin, NUpload, DataTableColumn, NTable } from 'naive-ui'
import { useDccStore, useOrgsStore } from '@/stores/api'
import { IDcc } from '@/models/dcc'
import UpdateForm from '@/components/dcc/UpdatePopup.vue';
import UploadForm from '@/components/dcc/UploadPopup.vue';
import EmailForm from '@/components/dcc/EmailPopup.vue';
import Details from '@/components/dcc/DetailedInfo.vue';
import ApproveForm from '@/components/dcc/ApprovePopup.vue';
import AssessmentForm from '@/components/dcc/AssessmentPopup.vue';
import { Add24Regular, SlideSearch24Regular, EqualCircle20Regular } from '@vicons/fluent';
import { IEcd } from '@/models/ecd'
import { getBooleanFilterMenuFunc, getStringFilterFunc, getStringFilterMenuFunc } from '@/stores/datatable'


const pagination = {
  pageSize: 12
}

const issueStats = ref<Record<string, any>>({})
const updatePopup = ref()
const uploadPopup = ref()
const emailPopup = ref()
const approvePopup = ref()
const assessmentPopup = ref()
const table = ref()
const syncStatus = ref({
  isFirstSynced: true,
  isSyncing: false,
})
const filterValue = ref<Record<string, any>>({ active: true } as IDcc);
const expandedRowKeys = ref<Array<string | number>>([])
let sessionID: string

const onFilter = (attrib: string, filterData: any) => {
  filterValue.value[attrib] = filterData
  filterAttr()
}

const columns: any[] = [
  {
    type: 'expand',
    multiple: false,
    expandable: (row: IDcc) => row.active && issueStats.value[row.issue],
    renderExpand: (row: IDcc) => {
      return h(Details, { dcc: issueStats.value[row.issue] })
    },
    disabled: true
  },
  {
    title: 'Issue',
    key: 'issue',
    filter: getStringFilterFunc('issue'),
    renderFilterMenu: getStringFilterMenuFunc("issue", filterValue, onFilter),
    ellipsis: {
      tooltip: true
    },
    width: 100
  },
  {
    title: 'ECD Name',
    key: 'ecd_name',
    filter: getStringFilterFunc('ecd_name'),
    renderFilterMenu: getStringFilterMenuFunc("ecd_name", filterValue, onFilter),
    ellipsis: {
      tooltip: true
    },
    resizable: true,
    width: 300,
    minWidth: 120,
    maxWidth: 600
  },
  {
    title: 'DCC Path',
    key: 'dcc_path',
    filter: getStringFilterFunc('dcc_path'),
    renderFilterMenu: getStringFilterMenuFunc("dcc_path", filterValue, onFilter),
    ellipsis: {
      tooltip: true
    },
    resizable: true,
    width: 300,
    minWidth: 120,
    maxWidth: 600
  },
  {
    title: 'Activeness',
    key: 'active',
    filter(value: boolean, row: IDcc) {
      return (row.active == value)
    },
    renderFilterMenu: getBooleanFilterMenuFunc('active', filterValue, onFilter),
    render(row: any) {
      return h(
        NTag,
        {
          style: {
            marginRight: '6px'
          },
          type: row.active ? 'success' : 'info',
          bordered: false
        },
        {
          default: () => row.active ? "Active" : "Passive",
        }
      )
    },
    ellipsis: {
      tooltip: true
    },
    width: 130
  },
  {
    title: 'Summary',
    key: 'summary',
    render(row: IDcc) {
      if (!syncStatus.value.isFirstSynced) {
        if (row.active) {
          let summary: boolean | null = null
          if (issueStats.value[row.issue]) {
            summary = !issueStats.value[row.issue].fields.subtasks.some((item: any) => item.fields.status.name === "Open")
          }
          if (summary == null) {
            return h(
              NSpin,
              {
                size: 20
              },
              {
                default: () => "Loading",
              }
            )
          } else {
            return h(
              NTag,
              {
                style: {
                  marginRight: '6px'
                },
                type: summary ? 'success' : 'warning',
                bordered: false
              },
              {
                default: () => summary ? "Completed" : "Progressing",
              }
            )
          }
        }
      } else {
        return "Syncing is required"
      }
    },
    ellipsis: {
      tooltip: true
    },
  },
  {
    title: 'Action',
    key: 'actions',
    minWidth: 240,
    render(row: IDcc) {
      return h(NSpace, { itemStyle: "width: 100px" }, {
        default: () => [h(
          NButton,
          {
            ghost: true,
            size: 'small',
            focusable: false,
            style: "width: 100%",
            onClick: () => {
              goPage(row.issue)
            }
          },
          { default: () => 'Go page' }
        ), h(
          NButton,
          {
            ghost: true,
            size: 'small',
            type: 'info',
            focusable: false,
            style: "width: 100%",
            onClick: () => {
              emailPopup.value?.openModal(row)
            }
          },
          { default: () => 'Send email' }
        ), h(
          NButton,
          {
            ghost: true,
            size: 'small',
            type: 'warning',
            focusable: false,
            onClick: () => {
              updatePopup.value?.openModal(row)
            },
            style: "width: 100%"
          },
          { default: () => 'Update' }
        ), h(
          NButton,
          {
            ghost: true,
            size: 'small',
            type: 'error',
            focusable: false,
            style: "width: 100%",
            onClick: () => {
              window.$dialog.warning({
                title: "Delete",
                content: "Are you sure to delete?",
                positiveText: "Yes",
                negativeText: "No",
                onPositiveClick: () => {
                  store.deleteDcc(row.id).then(() => {
                    delete issueStats.value[row.issue]
                  }).catch((err: any) => {
                    console.error("Error while deleting ", row.issue, ": ", err)
                  })
                },
              })
            }
          },
          { default: () => 'Delete' }
        )]
      })
    }
  }
]

const store = useDccStore()
const orgstore = useOrgsStore()

function goPage(url: string) {
  url = "https://taijiraprod.dmntai.intra/browse/" + url
  const newWindow = window.open(url, '_blank');
  if (newWindow !== null) {
    newWindow.focus();
  }
}

function filterAttr() {
  table.value?.filter(filterValue.value)
}

function showpUploadForm() {
  uploadPopup.value?.setActive(true)
}

onMounted(async () => {
  filterAttr()
  await store.fetchDcc()
  const storedSessionID = localStorage.getItem("jira>session_id")
  sessionID = storedSessionID ? storedSessionID : ""
})

async function syncAll() {
  syncStatus.value.isFirstSynced = false
  syncStatus.value.isSyncing = true
  issueStats.value = {}
  let tableData = store.getDccList.filter(issue => issue.active == true)

  const rows = tableData.map(row => ({ "issue": row.issue, "dcc_path": row.dcc_path } as IDcc))

  for (const row of rows) {
    try {
      const res = await store.getIssue(row)
      issueStats.value[row.issue] = res
    } catch (err) {
      issueStats.value[row.issue] = null
      continue
    }
  }
  syncStatus.value.isSyncing = false
}

function onSuccessUpload(data: IEcd) {
  if (approvePopup.value) {
    approvePopup.value.openModal(data)
  }
}

async function onSuccessAdd(row: IDcc) {
  row = { "issue": row.issue, "dcc_path": row.dcc_path } as IDcc
  const res = await store.getIssue(row)
  issueStats.value[row.issue] = res
}

async function onApproved(data: any) {
  window.$loadingBar.start()
  try {
    data.sessionId = sessionID
    let row = await store.createIssue(data)
    row = { "issue": row.issue, "dcc_path": row.dcc_path } as IDcc
    const res = await store.getIssue(row)
    issueStats.value[row.issue] = res

    window.$loadingBar.finish()
  }
  catch (err) {
    console.log(err)
    window.$loadingBar.error()
  }
}

const rowPropsAttr = (rowData: IDcc, rowIndex: number) => {
  return {
    onDblclick: () => {
      const isExpanded = expandedRowKeys.value.some(id => id === rowData.id);
      if (isExpanded) {
        expandedRowKeys.value = expandedRowKeys.value.filter(id => id !== rowData.id);
      } else {
        expandedRowKeys.value.push(rowData.id)
      }
    },
  }
}

function onUpdateExpandedRowKeys(keys: Array<string | number>) {
  expandedRowKeys.value = keys
}
</script>

<template>
  <n-card>
    <n-space>
      <n-button @click="() => { showpUploadForm() }">
        <template #icon>
          <n-icon size=24>
            <Add24Regular />
          </n-icon>
        </template>
        New
      </n-button>
      <n-button @click="() => { assessmentPopup?.openUpload() }">
        <template #icon>
          <n-icon size=24>
            <SlideSearch24Regular />
          </n-icon>
        </template>
        Assessment
      </n-button>
      <n-button @click="() => { syncAll() }" :disabled="syncStatus.isSyncing">
        <template #icon>
          <n-icon size=24>
            <EqualCircle20Regular />
          </n-icon>
        </template>
        Sync
      </n-button>
    </n-space>
    <n-flex justify="end">
      <n-text><strong>Total: </strong>{{ store.getDccList.length }}</n-text>
    </n-flex>

    <n-data-table ref="table" :loading="store.isLoading" striped :columns="columns" :data="store.getDccList"
      :pagination="pagination" :row-key="(row) => row.id" size="small" :expanded-row-keys="expandedRowKeys"
      @update:expanded-row-keys="onUpdateExpandedRowKeys" :row-props="rowPropsAttr" />
  </n-card>

  <UpdateForm ref="updatePopup" />
  <UploadForm ref="uploadPopup" :uploadUrl="axios.defaults.baseURL + '/dcc/upload/'" :onUploadSuccess="onSuccessUpload"
    :onAddSuccess="onSuccessAdd" title="Upload a DCC"
    description="Additionally, this process will create a Jira task for DCC" />
  <EmailForm ref="emailPopup" />
  <ApproveForm ref="approvePopup" :onApprove="onApproved" />
  <AssessmentForm ref="assessmentPopup" />
</template>