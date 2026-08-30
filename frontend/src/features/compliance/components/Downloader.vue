<template>
  <n-modal
    v-model:show="popup.visible"
    preset="card"
    :title="`Export ${popup.content}`"
    class="app-modal"
    :mask-closable="false"
    transform-origin="center"
  >
    <n-alert :title="popup.title" :type="popup.status">
      <template #icon>
        <n-spin v-if="popup.status == ''" size="tiny" />
      </template>
      <n-text v-if="popup.status == ''">
        Building the current project register from the canonical compliance API.
      </n-text>
      <n-text v-else-if="popup.status == 'success'">
        The current register snapshot is ready to download.
      </n-text>
      <n-text v-else>{{ popup.error }}</n-text>
    </n-alert>
    <n-card size="small" embedded style="margin-top: 16px">
      <n-space vertical>
        <n-text>✓ Includes all active documents, independent of the current table page</n-text>
        <n-text>✓ Uses server-authorized project data</n-text>
        <n-text>✓ Contains canonical document identifiers and versions</n-text>
        <n-text depth="3">
          Import validation is a separate preview/confirm flow; do not assume arbitrary workbook
          edits are accepted.
        </n-text>
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
import { ArrowDown24Regular } from '@vicons/fluent'
import { formatApiError } from '@/shared/api/apiError'
import { exportCompdocWorkbook } from '@/features/compliance/api/compdocFiles'

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
    const project = String(route.params.project || '')
    const workbook = await exportCompdocWorkbook(project)
    if (sequence !== requestSequence) return

    releaseDownload()
    urlObject = URL.createObjectURL(workbook)
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
