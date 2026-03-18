<script setup lang="ts">
import { h, ref, onMounted, onUnmounted } from 'vue'
import { NButton, NDataTable, NSpace, NTag, NUpload, NIcon, NEllipsis, DataTableColumns } from 'naive-ui'
import { useDdfStore } from '@/stores/api'
import { setProjectName } from '@/stores/user'
import { popupStore } from '@/stores/popupStore'
import { IDdf } from '@/models/ddf'
import UpdateForm from '@/components/ddf/DDFPopup.vue';
import UploadPopup from '@/components/ddf/UploadPopup.vue';
import Details from '@/components/ddf/DetailedInfo.vue';
import Graph from '@/components/ddf/Graph.vue';
import { ChannelAdd24Regular, Add24Regular, DataBarVertical24Regular, Edit24Regular, Delete24Regular, Eye24Regular } from '@vicons/fluent';
import { RouterLink, RouterView, useRouter, useRoute } from 'vue-router'
import { FilterOptionValue, RowData } from 'naive-ui/es/data-table/src/interface'
import { getDateFilterFunc, getDateFilterMenuFunc, getStringFilterFunc, getStringFilterMenuFunc } from '@/stores/datatable'

const route = useRoute()
const popup = popupStore()
const store = useDdfStore()
const viewPopup = ref()
const uploadPopup = ref()
const table = ref()
const graph = ref()

const filterValue = ref<Record<string, any>>({});

setProjectName(route.params.project as string)

const pagination = {
  pageSize: 10
}

const onFilter = (attrib: string, filterData: any) => {
  filterValue.value[attrib] = filterData
  filterAttr()
}

const onClean = (attrib: string) => {
  filterValue.value[attrib] = null
  filterAttr()
}

const columns: DataTableColumns<IDdf> = [
  {
    type: 'expand',
    expandable: (row) => true,
    renderExpand: (row) => {
      return h(Details, { ddf: row })
    }
  },
  {
    title: 'Project',
    key: 'project',
    width: 300,
    filter: getStringFilterFunc('project'),
    renderFilterMenu: getStringFilterMenuFunc("project", filterValue, onFilter),
    ellipsis: {
      tooltip: true
    },
    resizable: true,
    minWidth: 200,
    maxWidth: 600
  },
  {
    title: 'Doc Name',
    key: 'doc_name',
    filter: getStringFilterFunc('doc_name'),
    renderFilterMenu: getStringFilterMenuFunc("doc_name", filterValue, onFilter),
    ellipsis: {
      tooltip: true
    },
    resizable: true,
    minWidth: 200,
    maxWidth: 600
  },
  {
    title: 'Doc No',
    key: 'doc_no',
    filter: getStringFilterFunc('doc_no'),
    renderFilterMenu: getStringFilterMenuFunc("doc_no", filterValue, onFilter),
    ellipsis: {
      tooltip: true
    },
    width: 120
  },
  {
    title: 'Doc Issue',
    key: 'doc_issue',
    filter: getStringFilterFunc('doc_issue'),
    renderFilterMenu: getStringFilterMenuFunc("doc_issue", filterValue, onFilter),
    ellipsis: {
      tooltip: true
    },
    width: 100,
  },
  {
    title: 'Doc Date',
    key: 'date',
    filter: getDateFilterFunc('date'),
    renderFilterMenu: getDateFilterMenuFunc("date", onFilter, onClean),
    width: 100,
  },
  {
    title: 'Commentor',
    key: 'commentor',
    filter: getStringFilterFunc('commentor'),
    renderFilterMenu: getStringFilterMenuFunc("commentor", filterValue, onFilter),
    width: 140,
    ellipsis: {
      tooltip: true
    },
  },
  {
    title: 'Comments',
    key: 'comments',
    filter: (value, row) => {
      return Boolean(~row.comments.indexOf(value as string))
    },
    width: 120,
    ellipsis: {
      tooltip: true
    },
    render(row: IDdf) {
      return h(NButton, {
        ghost: true,
        size: 'small',
        focusable: false,
        onClick: () => {
          const combinedArray = row.comments.map((element, index) => `[${row.comment_types[index]}] ${element[2]}`);
          popup.open("Comments", combinedArray)
        }
      },
        {
          default: () => "Show"
        })
    }
  },
  {
    title: 'Action',
    key: 'actions',
    minWidth: 120,
    render(row: IDdf) {
      const analyzeDisabled = ref(false)
      return h(NSpace, {}, {
        default: () => [h(
          NButton,
          {
            ghost: true,
            size: 'small',
            type: 'info',
            focusable: false,
            renderIcon: () => h(Eye24Regular),
            onClick: () => {
              viewPopup.value.openModal(row, "view")
            },
          },
          { default: () => null }
        ), h(
          NButton,
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
                  store.deleteDdf(row.id).then(() => {
                    console.log("Request deleted: ", row.doc_name)
                  }).catch((err: any) => {
                    console.error("Error while deleting ", row.doc_name, ": ", err)
                  })
                },
              })
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
            disabled: analyzeDisabled.value,
            //renderIcon: () => h(Eye24Regular),
            onClick: () => {
              analyzeDisabled.value = true
              store.assessment(row).then(res => {
                console.log(res)
                popup.open("Result", res, false)
              }).finally(() => {
                analyzeDisabled.value = false
              })
            },
          },
          { default: () => "Analyze" }
        )
        ]
      })
    }
  }
]

function filterAttr() {
  table.value.filter(filterValue.value)
}

function showpUploadForm() {
  uploadPopup.value.setActive(true)
}

function rowKey(row: IDdf) {
  return row.id
}

function handleFilterUpdate() {
  filterAttr()
}

function showAddDdfForm(mode: string) {
  viewPopup.value.openModal({}, mode)
}

function showAnalyzeBar() {
  const filteredTable = table.value.data.filter((ddf: Record<string, any>) => {
    for (const key in filterValue.value) {
      if (filterValue.value[key] && !ddf[key].includes(filterValue.value[key])) {
        //console.log(ddf[key], filterValue.value[key])
        return false;
      }
    }
    return true;
  });
  graph.value.openModal(filteredTable)
}

function deleteAllDdfs() {
  window.$dialog.error({
    title: "Delete",
    content: "Are you sure to delete all DDF?",
    positiveText: "Yes",
    negativeText: "No",
    onPositiveClick: async () => {
      const res = await store.deleteDdfs()
      console.log(res)
    },
  })
}

onMounted(() => {
  store.fetchDdf()
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
      <n-button @click="showAddDdfForm('new')" :focusable="false">
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
    </n-space>
    <n-space>
      <n-button ghost type="error" @click="deleteAllDdfs" :focusable="false">
        <template #icon>
          <n-icon size=24>
            <Delete24Regular />
          </n-icon>
        </template>
        Delete All
      </n-button>
    </n-space>
  </n-space>
  <n-flex justify="end">
    <n-text>
      <strong>Total: </strong>{{ store.getList.length }}
    </n-text>
  </n-flex>
  <n-data-table :loading="store.isLoading" striped type='expand' :tree='true' :columns="columns" :data="store.getList"
    :pagination="pagination" ref="table" :row-key="rowKey" />
  <UpdateForm ref="viewPopup" />
  <UploadPopup ref="uploadPopup" :uploadUrl="store.getUploadUrl" />
  <Graph ref="graph" />
</template>