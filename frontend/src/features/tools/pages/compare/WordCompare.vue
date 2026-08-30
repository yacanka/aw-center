<template>
  <n-card title="Word Comparison">
    <div class="comparison-uploads">
      <n-upload :show-file-list="true" :max="1" accept=".docx,.docm" @change="handleFirstChange">
        <n-upload-dragger>
          <n-text style="font-size: 16px"> Click or drag a file to this area to upload </n-text>
          <n-p depth="3" style="margin: 8px 0 0 0"> Old Word file </n-p>
        </n-upload-dragger>
      </n-upload>
      <n-upload :show-file-list="true" :max="1" accept=".docx,.docm" @change="handleSecondChange">
        <n-upload-dragger>
          <n-text style="font-size: 16px"> Click or drag a file to this area to upload </n-text>
          <n-p depth="3" style="margin: 8px 0 0 0"> New Word file </n-p>
        </n-upload-dragger>
      </n-upload>
    </div>
    <n-form ref="form" :model="parameters" style="margin-top: 18px">
      <n-grid responsive="self" item-responsive cols="12" x-gap="18">
        <n-form-item-gi path="equal_ratio" label="Equal Ratio" span="0:12 700:3">
          <n-input-number
            v-model:value="parameters.equal_ratio"
            min="0"
            max="1"
            step="0.01"
            placeholder="Ratio"
          />
        </n-form-item-gi>
        <n-form-item-gi path="weak_equal_ratio" label="Weak Equal Ratio" span="0:12 700:3">
          <n-input-number
            v-model:value="parameters.weak_equal_ratio"
            min="0"
            max="1"
            step="0.01"
            placeholder="Ratio"
          />
        </n-form-item-gi>
        <n-form-item-gi path="output_type" label="Output Type" span="0:12 700:6">
          <n-select
            v-model:value="parameters.output_type"
            :options="outputOptions"
            placeholder="Select Type"
          />
        </n-form-item-gi>
      </n-grid>
    </n-form>
    <n-flex justify="center" style="margin-top: 16px">
      <n-button
        @click="compareWords"
        :focusable="false"
        :disabled="file1.length == 0 || file2.length == 0 || !parameters.output_type"
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
import { compareWordFiles } from '@/features/tools/api/comparisonTools'
import { saveBlobAsFile } from '@/shared/services/download'

const file1 = ref<UploadFileInfo[]>([])
const file2 = ref<UploadFileInfo[]>([])

const parameters = ref({
  equal_ratio: 0.9,
  weak_equal_ratio: 0.6,
  output_type: null
})
const outputOptions = [
  { value: 'excel', label: 'Excel', ext: 'xlsx' },
  { value: 'word', label: 'Word', ext: 'docx' }
]

function handleFirstChange(value: { fileList: UploadFileInfo[] }) {
  file1.value = value.fileList
}

function handleSecondChange(value: { fileList: UploadFileInfo[] }) {
  file2.value = value.fileList
}

async function compareWords() {
  const firstFile = selectedUploadFile(file1.value)
  const secondFile = selectedUploadFile(file2.value)
  if (!firstFile || !secondFile) return
  window.$loadingBar.start()

  try {
    const blob = await compareWordFiles(firstFile, secondFile, parameters.value)
    saveBlobAsFile(blob, 'Comparison Result')
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
