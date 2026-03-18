<template>
  <n-card title="Word Translator">
    <n-space style="padding: 20px 0px 0 0px" justify="center" item-style="minWidth: 200px; width: 500px">
      <n-upload ref="uploadForm" :show-file-list="true" :max="1" accept=".doc,.docx" @change="handleFirstChange">
        <n-upload-dragger>
          <n-text style="font-size: 16px">
            Click or drag a file to this area to upload
          </n-text>
          <n-p depth="3" style="margin: 8px 0 0 0">
            Word file to be translated
          </n-p>
        </n-upload-dragger>
      </n-upload>
    </n-space>
    <n-form ref="form" :model="parameters" style="margin-top: 18px">
      <n-grid cols="12" x-gap=18>
        <n-form-item-gi path="translate_type" label="Translate Type" span=3 offset=4>
          <n-select v-model:value="parameters.translate_type" :options="translateOptions" placeholder="Select Type" />
        </n-form-item-gi>
        <n-form-item-gi span=1>
          <n-button @click="translate" :focusable="false" :disabled="file.length == 0 || !parameters.translate_type"
            style="width: 100%">
            Translate
          </n-button>
        </n-form-item-gi>
        <n-grid-item span=12>
          <n-ellipsis v-if="loadingBar.show" style=" margin: 0px 0px 0px 0px"> {{
            loadingBar.content
          }}</n-ellipsis>
        </n-grid-item>
        <n-grid-item span=12>
          <n-progress v-if="loadingBar.show" type="line" :status="loadingBar.status" :percentage="loadingBar.percentage"
            indicator-placement="outside" :height="30" :processing="loadingBar.status == 'default' ? true : false">
          </n-progress>
        </n-grid-item>
      </n-grid>
    </n-form>
  </n-card>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { NModal, NotificationType, UploadFileInfo } from 'naive-ui';
import axios from 'axios'
import { useExcelStore } from '@/stores/api'
import { popupStore } from '@/stores/popupStore';
import { Document24Regular } from '@vicons/fluent';
import { toTitleCase } from '@/utils/text';

const store = useExcelStore()
const uploadForm = ref(); // UploadForm'a erişim için
const popup = popupStore()

const file = ref<UploadFileInfo[]>([])

const parameters = ref({
  translate_type: null,
})
const translateOptions = [
  { value: "tr2en", label: "Turkish -> English" },
  { value: "en2tr", label: "English -> Turkish" },
]

onMounted(() => {
  //  uploaderFormRef.value.reset()
});

function handleFirstChange(value: { fileList: UploadFileInfo[] }) {
  file.value = value.fileList
}


const loadingBar = ref({
  show: false,
  status: "",
  percentage: 0,
  content: ""
})
type StreamData = {
  status: string
  type: string
  percentage: number
  content: any
  filename: string
}

function translate() {
  loadingBar.value.show = true
  loadingBar.value.status = "default"
  loadingBar.value.percentage = 0

  const formData = new FormData()
  formData.append('file', file.value[0].file)
  formData.append('parameters', JSON.stringify(parameters.value))

  axios.post(`${axios.defaults.baseURL}/word/create_queue/`, formData
  ).then((res) => {
    const eventSource = new EventSource(`${axios.defaults.baseURL}/word/translate/${res.data}`);
    eventSource.onmessage = function (event) {
      const data: StreamData = JSON.parse(event.data);
      console.log(data)
      if (data.status == "progress") {
        loadingBar.value.percentage = data.percentage
        loadingBar.value.content = data.content
      } else if (["success", "warning", "error"].includes(data.status)) {
        eventSource.close()
        loadingBar.value.percentage = 100
        loadingBar.value.status = data.status
        loadingBar.value.content = ""

        if (data.status == "success") {
          const byteCharacters = atob(data.content)
          const byteArray = new Uint8Array([...byteCharacters].map(c => c.charCodeAt(0)))
          const blob = new Blob([byteArray], { type: 'text/plain' })

          const link = document.createElement("a")
          link.href = URL.createObjectURL(blob)
          link.download = data.filename
          link.click()
          link.remove()
          URL.revokeObjectURL(link.href)

          uploadForm?.value.clear()
          file.value = []
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
    window.$notification.error({
      title: 'Error',
      description: `Error while uploading file: ${err.response.data.message}`,
    })
  }).finally(() => {

  })
}

</script>

<style scoped></style>
