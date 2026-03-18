<template>
  <n-card title="Excel Comparison">
    <n-space style="padding: 20px 50px 0 50px" justify="center" item-style="minWidth: 200px; width: 25vw">
      <n-upload :show-file-list="true" :max="1" accept=".xlsm,.xlsx" @change="handleFirstChange">
        <n-upload-dragger>
          <n-text style="font-size: 16px">
            Click or drag a file to this area to upload
          </n-text>
          <n-p depth="3" style="margin: 8px 0 0 0">
            Old Excel file
          </n-p>
        </n-upload-dragger>
      </n-upload>
      <n-upload :show-file-list="true" :max="1" accept=".xlsm,.xlsx" @change="handleSecondChange">
        <n-upload-dragger>
          <n-text style="font-size: 16px">
            Click or drag a file to this area to upload
          </n-text>
          <n-p depth="3" style="margin: 8px 0 0 0">
            New Excel file
          </n-p>
        </n-upload-dragger>
      </n-upload>
    </n-space>
    <n-flex>
      <strong style="margin-top: 2px">Key Columns:</strong>
      <n-dynamic-tags v-model:value="parameters.keyColumns" />
    </n-flex>
    <n-flex justify="center" style="margin-top: 16px">
      <n-button @click="compareExcels" :focusable="false" :disabled="file1.length == 0 || file2.length == 0">
        Compare
      </n-button>
    </n-flex>
  </n-card>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { NModal, UploadFileInfo } from 'naive-ui';
import axios from 'axios'
import { useExcelStore } from '@/stores/api'
import { popupStore } from '@/stores/popupStore';
import { Document24Regular } from '@vicons/fluent';

const store = useExcelStore()
const uploaderFormRef = ref(null); // UploadForm'a erişim için
const popup = popupStore()

const file1 = ref<UploadFileInfo[]>([])
const file2 = ref<UploadFileInfo[]>([])
const parameters = ref({
  keyColumns: []
})

onMounted(() => {
  //  uploaderFormRef.value.reset()
});

function handleFirstChange(value: { fileList: UploadFileInfo[] }) {
  file1.value = value.fileList
}

function handleSecondChange(value: { fileList: UploadFileInfo[] }) {
  file2.value = value.fileList
}

function compareExcels() {
  window.$loadingBar.start()

  const formData = new FormData()
  formData.append('first', file1.value[0].file)
  formData.append('second', file2.value[0].file)
  formData.append('json', JSON.stringify(parameters.value))

  axios.post(`${axios.defaults.baseURL}/excel/compare/`, formData, {
    responseType: 'blob'
  }).then((res) => {
    console.log(res)
    window.$notification.success({
      title: 'Success',
      description: "Comparison completed",
      duration: 3000
    })

    const urlObj = URL.createObjectURL(res.data)
    const downloader = document.createElement('a')
    downloader.href = urlObj
    downloader.download = "Comparison Result.xlsx"
    document.body.appendChild(downloader)
    downloader.click()
    downloader.remove()
    URL.revokeObjectURL(urlObj)

    window.$loadingBar.finish()
  }).catch((err) => {
    console.error(err)
    window.$notification.error({
      title: 'Error',
      description: "Error while comparing files.",
      duration: 3000
    })

    window.$loadingBar.error()
  }).finally(() => {
  })
}

</script>

<style scoped></style>
