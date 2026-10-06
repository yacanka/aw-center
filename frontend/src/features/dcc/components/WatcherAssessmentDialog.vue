<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { UploadFileInfo } from 'naive-ui'
import { useProjectCatalogStore } from '@/features/projects/stores/projectCatalog'
import { hasProjectDccRole } from '@/features/projects/models/projectRegistry'
import { formatApiError } from '@/shared/api/apiError'
import { assessWatcherPdf } from '../api/watcher'

const catalog = useProjectCatalogStore()
const visible = ref(false)
const busy = ref(false)
const selectedProjects = ref<string[]>([])
const files = ref<UploadFileInfo[]>([])
const answer = ref('')
const error = ref('')
const assessedFile = ref('')
watch(
  [selectedProjects, files],
  () => {
    answer.value = ''
    error.value = ''
    assessedFile.value = ''
  },
  { deep: true }
)
const options = computed(() =>
  catalog.dccProjects
    .filter((project) => hasProjectDccRole(project.roles.dcc, 'operator'))
    .map((project) => ({ label: project.name, value: project.slug }))
)
function open(): void {
  selectedProjects.value = options.value.length === 1 ? [options.value[0].value] : []
  files.value = []
  answer.value = ''
  error.value = ''
  visible.value = true
}
async function submit(): Promise<void> {
  const file = files.value[0]?.file
  if (!file || !selectedProjects.value.length || busy.value) return
  busy.value = true
  error.value = ''
  answer.value = ''
  try {
    answer.value = (await assessWatcherPdf(file, selectedProjects.value)).assessment
    assessedFile.value = file.name
  } catch (reason) {
    error.value = formatApiError(reason)
  } finally {
    busy.value = false
  }
}
async function copyAssessment(): Promise<void> {
  try {
    await navigator.clipboard.writeText(answer.value)
    window.$message.success('Assessment copied.')
  } catch {
    window.$message.error('Copy was unavailable. Select the assessment text to copy it.')
  }
}
defineExpose({ open })
</script>
<template>
  <n-modal
    v-model:show="visible"
    preset="card"
    title="ECR assessment"
    :mask-closable="!busy"
    :closable="!busy"
    :close-on-esc="!busy"
    content-style="max-height: calc(100dvh - 160px); overflow-y: auto"
    :style="{ width: 'min(860px, 95vw)' }"
  >
    <n-space vertical :size="16">
      <n-alert type="info" :bordered="false"
        >AI assessment provides a draft for specialist review.</n-alert
      >
      <n-form-item label="Affected projects">
        <n-select
          v-model:value="selectedProjects"
          multiple
          :options="options"
          :disabled="busy"
          aria-label="Affected projects"
          :input-props="{ 'aria-label': 'Affected projects' }"
          placeholder="Select the projects in this ECR"
        />
      </n-form-item>
      <n-form-item label="ECR PDF">
        <n-upload
          v-model:file-list="files"
          accept=".pdf"
          :max="1"
          :default-upload="false"
          :disabled="busy"
        >
          <n-button :disabled="busy">Choose PDF</n-button>
        </n-upload>
      </n-form-item>
      <n-alert v-if="error" type="error" role="alert">{{ error }}</n-alert>
      <n-button
        type="primary"
        :loading="busy"
        :disabled="!files.length || !selectedProjects.length"
        @click="submit"
        >Assess document</n-button
      >
      <n-text v-if="busy" role="status"
        >Reviewing nine disciplines. This may take a few minutes.</n-text
      >
      <n-card v-if="answer" size="small" title="Assessment result">
        <template #header-extra
          ><n-button size="small" @click="copyAssessment">Copy assessment</n-button></template
        >
        <n-text depth="2">{{ assessedFile }}</n-text>
        <p class="assessment-answer">{{ answer }}</p>
      </n-card>
    </n-space>
  </n-modal>
</template>

<style scoped>
.assessment-answer {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  line-height: 1.8;
  margin-bottom: 0;
}
</style>
