<template>
  <n-space vertical>
    <n-upload
      accept=".docx"
      :default-upload="false"
      :show-file-list="false"
      :disabled="busy || active"
      @change="readFile"
    >
      <n-button :loading="busy" :disabled="active">Read meeting minutes (.docx)</n-button>
    </n-upload>
    <n-alert v-if="error || errorMessage" type="error">{{ error || errorMessage }}</n-alert>
    <template v-if="job?.kind === 'jira.read_meeting_minutes'">
      <n-text>{{ job.input_name }} · {{ job.message || job.status }}</n-text>
      <n-progress v-if="active" type="line" :percentage="job.progress" />
      <n-button text @click="openJobCenter">Open in Job Center</n-button>
      <JiraIssueDraftPanel v-if="job.status === 'succeeded'" :key="job.id" :job="job" />
    </template>
  </n-space>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import type { UploadFileInfo } from 'naive-ui'
import { usePageJob } from '@/features/jobs/composables/usePageJob'
import JiraIssueDraftPanel from '@/features/jobs/components/JiraIssueDraftPanel.vue'
import { formatApiError } from '@/shared/api/apiError'
import { readMeetingMinutes } from '../api/meetingMinutes'

const { job, active, errorMessage, openJobCenter, setJob } = usePageJob('minutes_job')
const busy = ref(false)
const error = ref('')
async function readFile({ file }: { file: UploadFileInfo }) {
  if (!file.file || busy.value) return
  busy.value = true
  error.value = ''
  try {
    setJob(await readMeetingMinutes(file.file))
  } catch (cause) {
    error.value = formatApiError(cause)
  } finally {
    busy.value = false
  }
}
</script>
