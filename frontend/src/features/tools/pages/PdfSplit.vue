<template>
  <n-flex class="app-page-container">
    <n-card title="PDF Splitter">
      <n-grid responsive="self" item-responsive cols="12" x-gap="12" y-gap="18">
        <n-grid-item span="12">
          <n-progress
            v-if="loadingBar.show"
            type="line"
            :status="loadingBar.status"
            :percentage="loadingBar.percentage"
            indicator-placement="outside"
            :height="30"
            :processing="loadingBar.status == 'default' ? true : false"
          >
          </n-progress>
        </n-grid-item>
        <n-grid-item span="12">
          <n-ellipsis v-if="loadingBar.status == 'default' ? true : false" style="margin-top: 4px">
            {{ loadingBar.content }}</n-ellipsis
          >
        </n-grid-item>
        <n-grid-item span="12">
          <n-upload :max="1" accept=".pdf" @change="handleFileChange" @remove="handleFileRemove">
            <n-upload-dragger>
              <n-text style="font-size: 16px"> Click or drag a file to this area to upload </n-text>
              <n-p depth="3" style="margin: 8px 0 0 0">
                Upload the PDF file for splitting into groups.
              </n-p>
            </n-upload-dragger>
          </n-upload>
        </n-grid-item>
        <n-gi span="0:12 640:5">
          <n-input-number
            v-model:value="splitter.parts"
            min="1"
            placeholder="Parts"
            :disabled="splitter.pages_per_parts ? true : false"
            style="width: 100%"
          />
        </n-gi>
        <n-gi span="0:12 640:5">
          <n-input-number
            v-model:value="splitter.pages_per_parts"
            min="1"
            placeholder="Pages per parts"
            :disabled="splitter.parts ? true : false"
            style="width: 100%"
          />
        </n-gi>
        <n-gi span="0:12 640:2">
          <n-button
            block
            type="info"
            ghost
            :disabled="
              loadingBar.status == 'default' ||
              (splitter.parts == null && splitter.pages_per_parts == null) ||
              fileList.length == 0
            "
            @click="splitPdf"
            >Split</n-button
          >
        </n-gi>
      </n-grid>
    </n-card>
  </n-flex>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { getFileNameAndExt } from '@/shared/utils/text'
import { selectedUploadFile } from '@/shared/utils/uploads'
import { UploadFileInfo } from 'naive-ui'
import { formatApiError } from '@/shared/api/apiError'
import { splitPdfArchive, type PdfSplitParameters } from '@/features/tools/api/pdfTools'
import { saveBlobAsFile } from '@/shared/services/download'

const splitter = ref<PdfSplitParameters>({
  parts: null,
  pages_per_parts: null
})

const loadingBar = ref({
  show: false,
  status: '',
  percentage: 0,
  content: ''
})

const fileList = ref<UploadFileInfo[]>([])

function handleFileChange(options: { fileList: UploadFileInfo[] }) {
  fileList.value = options.fileList
}

function handleFileRemove() {}

async function splitPdf() {
  const selectedFile = selectedUploadFile(fileList.value)
  if (!selectedFile) return
  window.$loadingBar.start()
  try {
    const { name } = getFileNameAndExt(fileList.value[0].name)
    saveBlobAsFile(await splitPdfArchive(selectedFile, splitter.value), name || 'Split')
    window.$notification.success({
      title: 'Success',
      description: 'Split completed',
      duration: 3000
    })
    window.$loadingBar.finish()
  } catch (error) {
    window.$notification.error({
      title: 'Error',
      description: `Error while uploading file: ${formatApiError(error)}`
    })
    window.$loadingBar.error()
  }
}
</script>
