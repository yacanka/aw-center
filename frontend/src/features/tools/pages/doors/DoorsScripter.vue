<template>
  <n-flex class="app-page-container">
    <n-card title="DOORS Script Generator (Excel)">
      <template #header-extra>
        <n-tooltip trigger="hover" :delay="500">
          <template #trigger>
            <n-button disabled> DXL Library </n-button>
          </template>
          Authenticated DXL library delivery is not available in this deployment.
        </n-tooltip>
      </template>
      <n-grid responsive="self" item-responsive cols="12" x-gap="12" y-gap="18">
        <n-grid-item span="12">
          <n-upload
            :max="1"
            accept=".xlsm,.xlsx"
            :custom-request="handleUploadReq"
            @change="handleFileChange"
            @remove="handleFileRemove"
          >
            <n-upload-dragger>
              <n-text style="font-size: 16px"> Click or drag a file to this area to upload </n-text>
              <n-p depth="3" style="margin: 8px 0 0 0">
                Upload the excel file you wish to synchronize with DOORS.
              </n-p>
            </n-upload-dragger>
          </n-upload>
        </n-grid-item>

        <n-grid-item span="0:12 700:5" v-if="fileList.length != 0">
          <n-h4 style="margin-bottom: -10px"> Excel Column Names </n-h4>
        </n-grid-item>
        <n-grid-item span="0:12 700:5" v-if="fileList.length != 0">
          <n-h4 style="margin-bottom: -10px"> DOORS Column Names </n-h4>
        </n-grid-item>
        <n-grid-item span="0:12 700:2" v-if="fileList.length != 0">
          <n-h4 style="margin-bottom: -10px"> Search Item </n-h4>
        </n-grid-item>

        <n-grid-item span="12" v-for="(column, index) in columns" :key="index">
          <n-grid responsive="self" item-responsive cols="12" x-gap="12" y-gap="18">
            <n-grid-item span="0:12 700:5">
              <n-input v-model:value="column.excel" readonly />
            </n-grid-item>
            <n-grid-item span="0:12 700:5">
              <n-input v-model:value="column.doors" />
            </n-grid-item>
            <n-grid-item span="0:12 700:2">
              <n-switch
                v-model:value="column.search"
                @update:value="(value: boolean) => handleSearchChange(index, value)"
              />
            </n-grid-item>
          </n-grid>
        </n-grid-item>
        <n-grid-item span="12" v-if="fileList.length != 0">
          <n-flex justify="center">
            <n-button type="success" ghost @click="createScript">Generate</n-button>
          </n-flex>
        </n-grid-item>
      </n-grid>
    </n-card>
  </n-flex>

  <n-modal
    v-model:show="modal.show"
    preset="card"
    title="Script"
    transform-origin="center"
    class="app-modal app-modal--large"
  >
    <template #header-extra>
      {{ modal.rowCount }} rows · {{ modal.mappingCount }} mappings
    </template>
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
import { createDoorsScript, getExcelColumns } from '@/features/tools/api/doorsScript'
import { UploadCustomRequestOptions, UploadFileInfo } from 'naive-ui'
import { selectedUploadFile } from '@/shared/utils/uploads'

type OptionItem = { excel: string; doors: string; search: boolean }

const columns = ref<OptionItem[]>([])
const fileList = ref<UploadFileInfo[]>([])

const modal = ref({
  show: false,
  content: '',
  rowCount: 0,
  mappingCount: 0
})

function handleFileChange(options: { fileList: UploadFileInfo[] }) {
  fileList.value = options.fileList
}

function handleFileRemove() {
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

function createScript() {
  const selectedFile = selectedUploadFile(fileList.value)
  if (!selectedFile) return
  const filtered = columns.value.filter((item: OptionItem) => item.doors != '')
  const formData = new FormData()
  formData.append('file', selectedFile)
  formData.append('json', JSON.stringify(filtered))
  createDoorsScript(formData)
    .then((result) => {
      modal.value.content = result.script
      modal.value.rowCount = result.row_count
      modal.value.mappingCount = result.mapping_count
      modal.value.show = true
      window.$message.success('Script created successfully.')
    })
    .catch(() => window.$message.error('The DOORS script could not be created.'))
}

function handleUploadReq({ file, onError }: UploadCustomRequestOptions) {
  const selectedFile = selectedUploadFile([file])
  if (!selectedFile) return onError()
  window.$loadingBar.start()
  const formData = new FormData()
  formData.append('file', selectedFile)
  getExcelColumns(formData)
    .then((res: string[]) => {
      const excelColumns = res
      if (excelColumns) {
        for (let i = 0; i < excelColumns.length; i++) {
          columns.value.push({ excel: excelColumns[i], doors: '', search: false })
        }
      }
      window.$message.success('Excel content successfully read.')
    })
    .catch(() => window.$message.error('The workbook columns could not be read.'))
    .finally(() => {
      window.$loadingBar.finish()
    })
}

async function copyToClipboard() {
  try {
    await navigator.clipboard.writeText(modal.value.content)
    window.$message.success('Script Copied')
  } catch (err) {
    console.error(err)
  }
}

onMounted(() => {})
</script>
