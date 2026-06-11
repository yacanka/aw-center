<template>
  <n-card title="Compdoc Analyzer">
    <n-upload ref="uploadForm" :show-file-list="true" :max="1" accept=".doc,.docx" @change="handleFirstChange">
      <n-upload-dragger>
        <n-text style="font-size: 16px">
          Click or drag a file to this area to upload
        </n-text>
        <n-p depth="3" style="margin: 8px 0 0 0">
          Compdoc Word file
        </n-p>
      </n-upload-dragger>
    </n-upload>
    <n-ellipsis v-if="loadingBar.show" style=" margin: 0px 0px 0px 0px"> {{
      loadingBar.content
    }}</n-ellipsis>
    <n-progress v-if="loadingBar.show" type="line" :status="loadingBar.status" :percentage="loadingBar.percentage"
      indicator-placement="outside" :height="30" :processing="loadingBar.status == 'default' ? true : false">
    </n-progress>
    <n-flex justify="center" style="margin: 16px">
      <n-button @click="compareWords" :focusable="false" :disabled="file1.length == 0 || loadingBar.status == ''">
        Analyze
      </n-button>
    </n-flex>
    <n-space vertical :size="12">
      <n-alert v-for="(checkItem, i) in checkList" :title="(i + 1) + '. ' + checkItem.title" :type="checkItem.status">
        <template #icon>
          <n-spin v-if="checkItem.status == null" :size="22" />
        </template>
        <n-progress type="line" :status="checkItem.status" :percentage="checkItem.score" indicator-placement="inside"
          :height="20" :processing="false">
        </n-progress>
        <n-collapse style="margin-top: 8px;">
          <n-collapse-item title="Details" name="details">
            <n-text style="white-space: pre-line"> {{ checkItem.description }} </n-text>
          </n-collapse-item>
        </n-collapse>
      </n-alert>
    </n-space>
  </n-card>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { NModal, UploadFileInfo, NotificationType } from 'naive-ui';
import axios from 'axios'
import { useExcelStore } from '@/stores/api'
import { popupStore } from '@/stores/popupStore';
import { Document24Regular, ImageAltText16Filled } from '@vicons/fluent';
import { toTitleCase } from '@/utils/text';
import { formatApiError } from '@/services/apiError'

type CheckItem = {
  title: string
  status: string
  description: string
  score: number
}

type StreamData = {
  status: string
  type: string
  percentage: number
  content: any
  filename: string
}

const store = useExcelStore()
const uploadForm = ref(); // UploadForm'a erişim için
const popup = popupStore()

const file1 = ref<UploadFileInfo[]>([])
const checkList = ref<CheckItem[]>([])

const loadingBar = ref({
  show: true,
  status: "default",
  percentage: 0,
  content: ""
})

onMounted(() => {
  //  uploaderFormRef.value.reset()
});

function handleFirstChange(value: { fileList: UploadFileInfo[] }) {
  file1.value = value.fileList
}

function compareWords() {
  checkList.value = []
  loadingBar.value.percentage = 0
  loadingBar.value.status = ""
  loadingBar.value.content = ""

  const formData = new FormData()
  formData.append('file', file1.value[0].file)

  axios.post(`${axios.defaults.baseURL}/word/create_queue/`, formData
  ).then((res) => {
    const eventSource = new EventSource(`${axios.defaults.baseURL}/word/analyze/${res.data}`);
    eventSource.onmessage = function (event) {
      const data: StreamData = JSON.parse(event.data);
      console.log(data)
      if (data.status == "progress") {
        loadingBar.value.percentage = data.percentage
        loadingBar.value.content = data.content

      } else if (data.status == "info") {
        const parsed = JSON.parse(data.content)
        const item: CheckItem = {} as CheckItem
        item.score = parsed["best_score"]
        item.score = Math.round(item.score * 100)
        item.title = parsed["query"]
        item.status = item.score > 60 ? "success" : item.score > 30 ? "warning" : "error"
        item.description = parsed["results"][0]
        checkList.value.push(item)

      } else if (["success", "warning", "error"].includes(data.status)) {
        eventSource.close()
        loadingBar.value.percentage = 100
        loadingBar.value.status = data.status
        loadingBar.value.content = ""

        if (data.status == "success") {
          console.log("SUCCESS")
        } else {
          window.$notification[data.status as NotificationType]({
            title: toTitleCase(data.status),
            description: data.content,
            duration: 3000
          })
        }
      }
    };
    eventSource.onerror = function (err) {
      console.log(err)
      loadingBar.value.status = "error"
      eventSource.close();
    };

  }).catch((err) => {
    console.error(err)
    loadingBar.value.status = "error"
    window.$notification.error({
      title: 'Error',
      description: `Error while uploading file: ${formatApiError(err)}`,
    })
  }).finally(() => {

  })
}

</script>

<style scoped></style>
