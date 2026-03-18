<template>
  <n-flex style="padding: 0px 300px">
    <n-card title="PDF Splitter">
      <n-grid cols=12 x-gap=12 y-gap="18">
        <n-grid-item span=12>
          <n-progress v-if="loadingBar.show" type="line" :status="loadingBar.status" :percentage="loadingBar.percentage"
            indicator-placement="outside" :height="30" :processing="loadingBar.status == 'default' ? true : false">
          </n-progress>
        </n-grid-item>
        <n-grid-item span=12>
          <n-ellipsis v-if="loadingBar.status == 'default' ? true : false" style="margin-top: 4px"> {{
            loadingBar.content }}</n-ellipsis>
        </n-grid-item>
        <n-grid-item span=12>
          <n-upload :max="1" accept=".pdf" @change="handleFileChange" @remove="handleFileRemove">
            <n-upload-dragger>
              <n-text style="font-size: 16px">
                Click or drag a file to this area to upload
              </n-text>
              <n-p depth="3" style="margin: 8px 0 0 0">
                Upload the PDF file for splitting into groups.
              </n-p>
            </n-upload-dragger>
          </n-upload>
        </n-grid-item>
        <n-gi span="3">
          <n-input-number v-model:value="splitter.parts" min="1" placeholder="Parts"
            :disabled="splitter.pages_per_parts ? true : false" />
        </n-gi>
        <n-gi span="3">
          <n-input-number v-model:value="splitter.pages_per_parts" min="1" placeholder="Pages per parts"
            :disabled="splitter.parts ? true : false" />
        </n-gi>
        <n-gi span=1>
          <n-button type="info" ghost
            :disabled="loadingBar.status == 'default' || (splitter.parts == '' && splitter.pages_per_parts == '') || fileList.length == 0"
            @click="splitPdf">Split</n-button>
        </n-gi>
      </n-grid>
    </n-card>
  </n-flex>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import axios from 'axios'
import { useRoute } from 'vue-router'
import { useDoorsStore, useExcelStore } from '@/stores/api'
import { getFileNameAndExt } from '@/utils/text'
import { UploadFileInfo } from 'naive-ui'
const route = useRoute()

const splitter = ref({
  parts: null,
  pages_per_parts: null
})

const loadingBar = ref({
  show: false,
  status: "",
  percentage: 0,
  content: ""
})

const fileList = ref<UploadFileInfo[]>([])

const doors = useDoorsStore()
const excel = useExcelStore()

function handleFileChange(options: { fileList: UploadFileInfo[] }) {
  fileList.value = options.fileList
}

function handleFileRemove(file: UploadFileInfo, fileList: Array<UploadFileInfo>, index: number) {
}

onMounted(() => {

})

function splitPdf() {
  window.$loadingBar.start()
  const formData = new FormData()
  formData.append('file', fileList.value[0].file)
  formData.append('parameters', JSON.stringify(splitter.value))
  axios.post(`${axios.defaults.baseURL}/pdf/split_pdf_zip/`, formData, {
    responseType: 'blob'
  }).then((res) => {
    window.$notification.success({
      title: 'Success',
      description: "Split completed",
      duration: 3000
    })

    const urlObj = URL.createObjectURL(res.data)
    const downloader = document.createElement('a')
    downloader.href = urlObj

    const { name, ext } = getFileNameAndExt(fileList.value[0].name)
    downloader.download = name || "Split"
    document.body.appendChild(downloader)
    downloader.click()
    downloader.remove()
    URL.revokeObjectURL(urlObj)

    window.$loadingBar.finish()
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