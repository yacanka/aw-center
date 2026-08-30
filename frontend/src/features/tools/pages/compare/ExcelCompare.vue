<template>
  <n-card title="Excel Comparison">
    <div class="comparison-uploads">
      <n-upload :show-file-list="true" :max="1" accept=".xlsm,.xlsx" @change="handleFirstChange">
        <n-upload-dragger>
          <n-text style="font-size: 16px"> Click or drag a file to this area to upload </n-text>
          <n-p depth="3" style="margin: 8px 0 0 0"> Old Excel file </n-p>
        </n-upload-dragger>
      </n-upload>
      <n-upload :show-file-list="true" :max="1" accept=".xlsm,.xlsx" @change="handleSecondChange">
        <n-upload-dragger>
          <n-text style="font-size: 16px"> Click or drag a file to this area to upload </n-text>
          <n-p depth="3" style="margin: 8px 0 0 0"> New Excel file </n-p>
        </n-upload-dragger>
      </n-upload>
    </div>
    <n-flex>
      <strong style="margin-top: 2px">Key Columns:</strong>
      <n-dynamic-tags v-model:value="parameters.keyColumns" />
    </n-flex>
    <n-flex justify="center" style="margin-top: 16px">
      <n-button
        @click="compareExcels"
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
import { compareExcelFiles } from '@/features/tools/api/comparisonTools'
import { saveBlobAsFile } from '@/shared/services/download'

const file1 = ref<UploadFileInfo[]>([])
const file2 = ref<UploadFileInfo[]>([])
const parameters = ref<{ keyColumns: string[] }>({
  keyColumns: []
})

function handleFirstChange(value: { fileList: UploadFileInfo[] }) {
  file1.value = value.fileList
}

function handleSecondChange(value: { fileList: UploadFileInfo[] }) {
  file2.value = value.fileList
}

async function compareExcels() {
  const firstFile = selectedUploadFile(file1.value)
  const secondFile = selectedUploadFile(file2.value)
  if (!firstFile || !secondFile) return
  window.$loadingBar.start()

  try {
    saveBlobAsFile(
      await compareExcelFiles(firstFile, secondFile, parameters.value.keyColumns),
      'Comparison Result.xlsx'
    )
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
