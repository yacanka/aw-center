<template>
  <n-flex justify="center">
    <n-card title="JIRA Subtask Generator from Excel" style="width: 90%;">
      <n-grid cols=6 x-gap=12 y-gap="18">
        <n-grid-item span=5>
          <n-input v-model:value="generator.url" type="url" placeholder="Enter Url" @keydown.enter.prevent />
        </n-grid-item>
        <n-grid-item span=1>
          <n-button type="info" ghost
            :disabled="loadingBar.status == 'default' || generator.url == '' || generator.JSESSIONID == '' || fileList.length == 0"
            @click="createSubtasks">Generate</n-button>
        </n-grid-item>
        <n-grid-item span=5>
          <n-progress v-if="loadingBar.show" type="line" :status="loadingBar.status" :percentage="loadingBar.percentage"
            indicator-placement="outside" :height="30" :processing="loadingBar.status == 'default' ? true : false">
          </n-progress>
        </n-grid-item>
        <n-grid-item span=1>
          <n-ellipsis v-if="loadingBar.status == 'default' ? true : false" style="margin-top: 4px"> {{
            loadingBar.content
          }}</n-ellipsis>
        </n-grid-item>
        <n-grid-item span=6>
          <n-upload :max="1" accept=".xlsm,.xlsx" :custom-request="handleUploadReq" @change="handleFileChange"
            @remove="handleFileRemove">
            <n-upload-dragger>
              <n-text style="font-size: 16px">
                Click or drag a file to this area to upload
              </n-text>
              <n-p depth="3" style="margin: 8px 0 0 0">
                Upload the Excel file containing the data to generate subtasks from.
              </n-p>
            </n-upload-dragger>
          </n-upload>
        </n-grid-item>

        <n-grid-item span=3 v-if="fileList.length != 0">
          <n-h4 style="margin-bottom: -10px">
            Excel Column Names
          </n-h4>
        </n-grid-item>
        <n-grid-item span=3 v-if="fileList.length != 0">
          <n-h4 style="margin-bottom: -10px">
            JIRA Field Names
          </n-h4>
        </n-grid-item>

        <n-grid-item span=6 v-for="(field, index) in generator.list" :key="index">
          <n-grid cols=6 x-gap=12 y-gap="18">
            <n-grid-item span=3>
              <n-input v-model:value="field.excel" readonly />
            </n-grid-item>
            <n-grid-item span=3>
              <n-select v-model:value="field.jira" :options="jiraOptions" placeholder="Select Field" clearable
                @update:value="(value: string) => handleFieldChange(index, value)" />
            </n-grid-item>
          </n-grid>
        </n-grid-item>
      </n-grid>
    </n-card>
  </n-flex>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import axios from 'axios'
import { useRoute } from 'vue-router'
import { useDoorsStore, useExcelStore } from '@/stores/api'
import { UploadCustomRequestOptions, UploadFileInfo } from 'naive-ui'

type ListItem = {
  excel: string, 
  jira: string | null
}


const route = useRoute()

const generator = ref({
  JSESSIONID: "",
  url: "",
  dueDate: null,
  assignee: "",
  list: [] as ListItem[],
})

const loadingBar = ref({
  show: false,
  status: "",
  percentage: 0,
  content: ""
})
const username = ref("Yaşar Can Kara (t02077)")

const columns = ref([])
const fileList = ref<UploadFileInfo[]>([])

const doors = useDoorsStore()
const excel = useExcelStore()
const modal = ref({
  show: false,
  content: ""
})

const jiraOptions = ref([
  { value: "summary", label: "Summary" },
  { value: "description", label: "Description" },
  { value: "assignee", label: "Assignee" },
  { value: "duedate", label: "Due Date" }
])

function handleFileChange(options: { fileList: UploadFileInfo[] }) {
  fileList.value = options.fileList
}

function handleFileRemove(file: UploadFileInfo, fileList: Array<UploadFileInfo>, index: number) {
  generator.value.list = []
  handleFieldChange(0, "")
}

function handleFieldChange(index: number, value: string) {
  for (let option of jiraOptions.value) {
    let locked = false
    generator.value.list.forEach((item, i) => {
      if (option.value == item.jira) {
        locked = true
      }
    })
    option.disabled = locked
  }
}

function handleUploadReq({ file, onFinish, onError }: UploadCustomRequestOptions) {
  window.$loadingBar.start()
  const formData = new FormData()
  formData.append('file', fileList.value[0].file)
  excel.getExcelColumns(formData).then((res) => {
    const excelColumns = res
    for (let i = 0; i < excelColumns.length; i++) {
      generator.value.list.push({ excel: excelColumns[i], jira: null })
    }
  }).finally(() => {
    window.$loadingBar.finish()
  })
}

onMounted(() => {
  const storedSessionID = localStorage.getItem("jira>session_id")
  generator.value.JSESSIONID = storedSessionID ? storedSessionID : ""
})

function createSubtasks() {
  const parameters = {...generator.value}
  parameters.list = parameters.list.filter(item => item.jira != null);
  const formData = new FormData()
  formData.append('file', fileList.value[0].file)
  formData.append('parameters', JSON.stringify(parameters))
  loadingBar.value.show = true
  loadingBar.value.status = "default"
  loadingBar.value.percentage = 0
  axios.post(`${axios.defaults.baseURL}/dcc/create_queue/`, formData
  ).then((res) => {
    const eventSource = new EventSource(`${axios.defaults.baseURL}/dcc/create_subtask_excel_stream/${res.data}`);
    eventSource.onmessage = function (event) {
      const data = JSON.parse(event.data);
      if (data.status == "progress") {
        loadingBar.value.percentage = data.percentage
        loadingBar.value.content = `${data.content}`
      } else if (data.status == "success") {
        eventSource.close()
        loadingBar.value.percentage = 100
        loadingBar.value.status = "success"
        loadingBar.value.content = ""
        window.$notification.success({
          title: 'Success',
          description: data.content,
          duration: 3000
        })
      }
      else if (data.status == "warning") {
        eventSource.close()
        loadingBar.value.percentage = 100
        loadingBar.value.status = "warning"
        loadingBar.value.content = ""
        window.$notification.warning({
          title: 'Warning',
          description: data.content,
          duration: 3000
        })
      } else if (data.status == "error") {
        eventSource.close()
        loadingBar.value.percentage = 100
        loadingBar.value.status = "error"
        loadingBar.value.content = ""
        window.$notification.error({
          title: 'Error',
          description: data.content,
          duration: 3000
        })
      } else if (data.status == "info") {
        username.value = `${data.content["displayName"]} (${data.content["name"]})`
      }
    };
    eventSource.onerror = function (err) {
      console.log(err)
      loadingBar.value.status = "error"
      eventSource.close();
    };

  }).catch((err) => {
    console.error(err)
    window.$notification.error({
      title: 'Error',
      description: `Error while uploading file: ${err.response.data.message}`,
    })
  }).finally(() => {
    console.log("END")
  })
}
</script>