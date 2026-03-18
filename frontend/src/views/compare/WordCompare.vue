<template>
  <n-card title="Word Comparison">
    <n-space style="padding: 20px 50px 0 50px" justify="center" item-style="minWidth: 200px; width: 25vw">
      <n-upload :show-file-list="true" :max="1" accept=".doc,.docx" @change="handleFirstChange">
        <n-upload-dragger>
          <n-text style="font-size: 16px">
            Click or drag a file to this area to upload
          </n-text>
          <n-p depth="3" style="margin: 8px 0 0 0">
            Old Word file
          </n-p>
        </n-upload-dragger>
      </n-upload>
      <n-upload :show-file-list="true" :max="1" accept=".doc,.docx" @change="handleSecondChange">
        <n-upload-dragger>
          <n-text style="font-size: 16px">
            Click or drag a file to this area to upload
          </n-text>
          <n-p depth="3" style="margin: 8px 0 0 0">
            New Word file
          </n-p>
        </n-upload-dragger>
      </n-upload>
    </n-space>
    <n-form ref="form" :model="parameters" style="margin-top: 18px">
      <n-grid cols="12" x-gap=18>
        <n-form-item-gi path="equal_ratio" label="Equal Ratio" span=1 offset="4">
          <n-input-number v-model:value="parameters.equal_ratio" min=0 max=1 step=0.01 placeholder="Ratio" />
        </n-form-item-gi>
        <n-form-item-gi path="weak_equal_ratio" label="Weak Equal Ratio" span=1>
          <n-input-number v-model:value="parameters.weak_equal_ratio" min=0 max=1 step=0.01 placeholder="Ratio" />
        </n-form-item-gi>
        <n-form-item-gi path="output_type" label="Output Type" span=2>
          <n-select v-model:value="parameters.output_type" :options="outputOptions" placeholder="Select Type" />
        </n-form-item-gi>
      </n-grid>
    </n-form>
    <n-flex justify="center" style="margin-top: 16px">
      <n-button @click="compareWords" :focusable="false"
        :disabled="file1.length == 0 || file2.length == 0 || !parameters.output_type">
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
  equal_ratio: 0.9,
  weak_equal_ratio: 0.6,
  output_type: null,
})
const outputOptions = [
  { value: "excel", label: "Excel", ext: "xlsx" },
  { value: "word", label: "Word", ext: "docx" },
]

onMounted(() => {
  //  uploaderFormRef.value.reset()
});

function handleFirstChange(value: { fileList: UploadFileInfo[] }) {
  file1.value = value.fileList
}

function handleSecondChange(value: { fileList: UploadFileInfo[] }) {
  file2.value = value.fileList
}

function compareWords() {
  window.$loadingBar.start()

  const formData = new FormData()
  formData.append('first', file1.value[0].file)
  formData.append('second', file2.value[0].file)
  formData.append('json', JSON.stringify(parameters.value))

  axios.post(`${axios.defaults.baseURL}/word/compare/`, formData, {
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
    downloader.download = "Comparison Result" // + (outputOptions.find(item => item.value == parameters.value.output_type))?.ext
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
