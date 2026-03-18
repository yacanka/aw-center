<template>
  <n-flex style="padding: 0px 300px">
    <n-card title="DOORS Script Generator (Excel)">
      <template #header-extra>
        <n-tooltip trigger="hover" :delay="500">
          <template #trigger>
            <n-button @click="downloadDxlLibrary"> DXL Library </n-button>
          </template>
          This library is required to run scripts which is created by generator. Click to download.
        </n-tooltip>
      </template>
      <n-grid cols=5 x-gap=12 y-gap="18">
        <n-grid-item span=6>
          <n-upload :max="1" accept=".xlsm,.xlsx" :custom-request="handleUploadReq" @change="handleFileChange"
            @remove="handleFileRemove">
            <n-upload-dragger>
              <n-text style="font-size: 16px">
                Click or drag a file to this area to upload
              </n-text>
              <n-p depth="3" style="margin: 8px 0 0 0">
                Upload the excel file you wish to synchronize with DOORS.
              </n-p>
            </n-upload-dragger>
          </n-upload>
        </n-grid-item>

        <n-grid-item span=2 v-if="fileList.length != 0">
          <n-h4 style="margin-bottom: -10px">
            Excel Column Names
          </n-h4>
        </n-grid-item>
        <n-grid-item span=2 v-if="fileList.length != 0">
          <n-h4 style="margin-bottom: -10px">
            DOORS Column Names
          </n-h4>
        </n-grid-item>
        <n-grid-item span=1 v-if="fileList.length != 0">
          <n-h4 style="margin-bottom: -10px">
            Search Item
          </n-h4>
        </n-grid-item>

        <n-grid-item span=5 v-for="(column, index) in columns" :key="index">
          <n-grid cols=5 x-gap=12 y-gap="18">
            <n-grid-item span=2>
              <n-input v-model:value="column.excel" readonly />
            </n-grid-item>
            <n-grid-item span=2>
              <n-input v-model:value="column.doors" />
            </n-grid-item>
            <n-grid-item span=1>
              <n-switch v-model:value="column.search"
                @update:value="(value: boolean) => handleSearchChange(index, value)" />
            </n-grid-item>
          </n-grid>
        </n-grid-item>
        <n-grid-item span=5 v-if="fileList.length != 0">
          <n-flex justify="center">
            <n-button type="success" ghost @click="createScript">Generate</n-button>
          </n-flex>
        </n-grid-item>
      </n-grid>
    </n-card>
  </n-flex>

  <n-modal v-model:show="modal.show" preset="card" title="Script" transform-origin="center" style="width: 50%">
    <n-scrollbar style="max-height: 500px; white-space: pre-wrap">
      {{ modal.content }}
    </n-scrollbar>
    <template #action>
      <n-flex justify="center">
        <n-button type="info" @click="copyToClipboard">Copy</n-button>
      </n-flex>
    </template>
  </n-modal>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import axios from 'axios'
import { useRoute } from 'vue-router'
import { useDoorsStore, useExcelStore } from '@/stores/api'
import { download } from 'naive-ui/es/_utils'
import { UploadCustomRequestOptions, UploadFileInfo } from 'naive-ui'

type OptionItem = { excel: string, doors: string, search: boolean }

const route = useRoute()

const columns = ref<OptionItem[]>([])
const fileList = ref<UploadFileInfo[]>([])

const doors = useDoorsStore()
const excel = useExcelStore()
const modal = ref({
  show: false,
  content: ""
})

function handleFileChange(options: { fileList: UploadFileInfo[] }) {
  fileList.value = options.fileList
}

function handleFileRemove(file: UploadFileInfo, fileList: Array<UploadFileInfo>, index: number) {
  columns.value = []
}

function handleSearchChange(index: number, value: boolean) {
  if (value) {
    columns.value.forEach((item: OptionItem, i: number) => {
      item.search = i === index
    })
  } else {
    columns.value[index].search = false
  }
}

async function downloadDxlLibrary() {
  try {
    const res = await axios.get(`${axios.defaults.baseURL}/download/yck.dxl`, {
      responseType: 'blob'
    })

    const urlObj = URL.createObjectURL(res.data)
    const downloadButton = document.createElement('a')
    downloadButton.href = urlObj
    downloadButton.download = "yck.dxl"
    document.body.appendChild(downloadButton)
    downloadButton.click()
    downloadButton.remove()
    URL.revokeObjectURL(urlObj)
  } catch {
    window.$notification.error({
      duration: 3000,
      title: "Error",
      content: "Something went wrong.",
    })
  }
}

function createScript() {
  const filtered = columns.value.filter((item: OptionItem) => item.doors != "");
  const formData = new FormData()
  formData.append('file', fileList.value[0].file)
  formData.append('json', JSON.stringify(filtered))
  doors.createScript(formData).then(res => {
    modal.value.content = res
    modal.value.show = true
  })
}

function handleUploadReq({ file, onFinish, onError }: UploadCustomRequestOptions) {
  window.$loadingBar.start()
  const formData = new FormData()
  formData.append('file', fileList.value[0].file)
  excel.getExcelColumns(formData).then((res: string[]) => {
    const excelColumns = res
    if (excelColumns) {
      for (let i = 0; i < excelColumns.length; i++) {
        columns.value.push({ excel: excelColumns[i], doors: "", search: false })
      }
    }
  }).finally(() => {
    window.$loadingBar.finish()
  })
}

async function copyToClipboard() {
  try {
    await navigator.clipboard.writeText(modal.value.content)
    window.$message.success("Script Copied")
  } catch (err) {
    console.error(err)
  }
}

onMounted(() => {

})
</script>