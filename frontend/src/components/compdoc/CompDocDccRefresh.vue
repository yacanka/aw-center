<template>
  <n-space vertical size="small">
    <n-button
      v-if="trace.can_refresh_preview"
      size="small"
      type="primary"
      :loading="refreshing"
      @click="refreshPreview"
    >
      Create current-source preview
    </n-button>
    <n-text v-else-if="statusMessage" depth="3">{{ statusMessage }}</n-text>
  </n-space>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useNotification } from 'naive-ui'
import { formatApiError } from '@/services/apiError'
import {
  refreshCompdocDccTrace,
  type CompdocDccTrace,
  type TraceRefreshStatus
} from '@/services/compdocTraceability'

const props = defineProps<{ trace: CompdocDccTrace }>()
const router = useRouter()
const notification = useNotification()
const refreshing = ref(false)
const statusMessage = computed(() => refreshStatusMessage(props.trace.refresh_status))

async function refreshPreview(): Promise<void> {
  refreshing.value = true
  try {
    const job = await refreshCompdocDccTrace(props.trace.id)
    notification.success({ title: 'Current-source preview ready', duration: 4000 })
    await router.push({ name: 'dcc', query: { dcc_job: job.id } })
  } catch (error) {
    notification.error({ title: 'Preview could not be created', content: formatApiError(error) })
  } finally {
    refreshing.value = false
  }
}

function refreshStatusMessage(status: TraceRefreshStatus): string {
  if (status === 'source_active') return 'Wait for the original DCC job to finish.'
  if (status === 'source_archived') return 'The retained JIRA snapshot is no longer available.'
  if (status === 'owner_required') return 'Only the original DCC creator can refresh this preview.'
  if (status === 'permission_required') return 'DCC creation permission is required to refresh.'
  return ''
}
</script>
