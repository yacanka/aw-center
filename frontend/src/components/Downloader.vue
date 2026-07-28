<template>
  <n-modal
    v-model:show="popup.visible"
    preset="card"
    :title="`Export ${popup.content}`"
    :style="{ width: '700px' }"
    :mask-closable="false"
    transform-origin="center"
  >
    <n-alert :title="popup.title" :type="popup.status">
      <template #icon>
        <n-spin v-if="popup.status == ''" size="tiny" />
      </template>
      <n-text v-if="popup.status == ''">
        Building a styled, editable workbook from the complete project register.
      </n-text>
      <n-text v-else-if="popup.status == 'success'">
        Your single-sheet workbook can be edited and imported directly back into AW Center.
      </n-text>
      <n-text v-else>{{ popup.error }}</n-text>
    </n-alert>
    <n-card size="small" embedded style="margin-top: 16px">
      <n-space vertical>
        <n-text>✓ Frozen headers, filters, status colors, and editable dropdowns</n-text>
        <n-text>✓ Every exported column is recognized by the current import contract</n-text>
        <n-text>✓ One worksheet with lossless multiline status history</n-text>
      </n-space>
    </n-card>
    <n-flex justify="center" style="margin-top: 24px">
      <n-button :disabled="!popup.download" @click="downloadExcel">
        <template #icon>
          <ArrowDown24Regular />
        </template>
        Download
      </n-button>
    </n-flex>
  </n-modal>
</template>

<script setup lang="ts">
import { onBeforeUnmount, ref } from 'vue'
import { useRoute } from 'vue-router'
import axios from 'axios'
import { ArrowDown24Regular } from '@vicons/fluent'
import { formatApiError } from '@/services/apiError'

const popup = ref({
  visible: false,
  download: false,
  title: '',
  status: '',
  content: '',
  error: ''
})

const route = useRoute()

let downloadButton: HTMLAnchorElement | null = null
let urlObject: string | null = null
let requestSequence = 0

async function prepareExcel(sequence: number) {
  try {
    const project = encodeURIComponent(String(route.params.project || ''))
    const response = await axios.get(`/${project}/compdocs/excel/`, { responseType: 'blob' })
    if (sequence !== requestSequence) return

    releaseDownload()
    urlObject = URL.createObjectURL(response.data)
    downloadButton = document.createElement('a')
    downloadButton.href = urlObject
    downloadButton.download = `${(route.params.project as string).toUpperCase()} Compliance Documents.xlsx`
    popup.value.download = true
    popup.value.title = 'Ready'
    popup.value.status = 'success'
  } catch (cause) {
    if (sequence !== requestSequence) return
    popup.value.error = formatApiError(cause)
    popup.value.title = 'Error'
    popup.value.status = 'error'
  }
}

async function downloadExcel() {
  downloadButton?.click()
  releaseDownload()
  popup.value.visible = false
}

function openModal(content: string) {
  const sequence = ++requestSequence
  releaseDownload()
  popup.value = {
    visible: true,
    title: `Preparing ${content}`,
    content: content,
    status: '',
    download: false,
    error: ''
  }
  prepareExcel(sequence)
}

function releaseDownload() {
  downloadButton?.remove()
  if (urlObject) URL.revokeObjectURL(urlObject)
  downloadButton = null
  urlObject = null
}

onBeforeUnmount(() => {
  requestSequence += 1
  releaseDownload()
})

defineExpose({
  openModal
})
</script>
