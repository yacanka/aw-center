<template>
  <n-card title="Pdf Comparison">
    <div class="comparison-uploads">
      <n-upload :show-file-list="true" :max="1" accept=".pdf" @change="handleFirstChange">
        <n-upload-dragger>
          <n-text style="font-size: 16px"> Click or drag a file to this area to upload </n-text>
          <n-p depth="3" style="margin: 8px 0 0 0"> Old Pdf file </n-p>
        </n-upload-dragger>
      </n-upload>
      <n-upload :show-file-list="true" :max="1" accept=".pdf" @change="handleSecondChange">
        <n-upload-dragger>
          <n-text style="font-size: 16px"> Click or drag a file to this area to upload </n-text>
          <n-p depth="3" style="margin: 8px 0 0 0"> New Pdf file </n-p>
        </n-upload-dragger>
      </n-upload>
    </div>
    <n-flex justify="center" style="margin-top: 16px">
      <n-button
        @click="comparePdfs"
        :focusable="false"
        :disabled="file1.length == 0 || file2.length == 0"
      >
        Compare
      </n-button>
    </n-flex>
  </n-card>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { UploadFileInfo } from 'naive-ui'
import { selectedUploadFile } from '@/shared/utils/uploads'
import { comparePdfFiles } from '@/features/tools/api/comparisonTools'
import { saveBlobAsFile } from '@/shared/services/download'

const file1 = ref<UploadFileInfo[]>([])
const file2 = ref<UploadFileInfo[]>([])

function handleFirstChange(value: { fileList: UploadFileInfo[] }) {
  file1.value = value.fileList
}

function handleSecondChange(value: { fileList: UploadFileInfo[] }) {
  file2.value = value.fileList
}

async function comparePdfs() {
  const firstFile = selectedUploadFile(file1.value)
  const secondFile = selectedUploadFile(file2.value)
  if (!firstFile || !secondFile) return
  window.$loadingBar.start()

  try {
    saveBlobAsFile(await comparePdfFiles(firstFile, secondFile), 'Comparison Result')
    window.$notification.success({
      title: 'Success',
      description: 'Comparison completed',
      duration: 3000
    })
    window.$loadingBar.finish()
  } catch {
    window.$notification.error({
      title: 'Error',
      description: 'Error while comparing files.',
      duration: 3000
    })
    window.$loadingBar.error()
  }
}
</script>

<style scoped>
.comparison-uploads {
  display: grid;
  gap: 18px;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  padding-top: 20px;
}

@media (max-width: 640px) {
  .comparison-uploads {
    grid-template-columns: 1fr;
  }
}
</style>
