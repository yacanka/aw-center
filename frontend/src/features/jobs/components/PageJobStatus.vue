<template>
  <n-card v-if="job" size="small" :title="job.title" embedded>
    <n-space vertical>
      <n-flex justify="space-between" align="center">
        <n-tag :type="statusType">{{ statusLabel }}</n-tag>
        <n-text depth="3">Attempt {{ job.attempt }}/{{ job.max_attempts }}</n-text>
      </n-flex>
      <n-progress
        type="line"
        :percentage="job.progress"
        :status="progressStatus"
        :processing="active"
      />
      <n-text>{{ job.message || 'Waiting for a worker.' }}</n-text>
      <n-alert v-if="job.recovery_hint" type="warning" :bordered="false">
        {{ job.recovery_hint }}
      </n-alert>
      <n-flex justify="end">
        <n-button @click="$emit('open')">Show in Job Center</n-button>
        <n-button v-if="job.can_cancel" type="error" :loading="cancelling" @click="$emit('cancel')">
          Cancel
        </n-button>
        <n-button
          v-if="job.download_url"
          type="success"
          :loading="downloading"
          @click="$emit('download')"
        >
          {{ downloadLabel }}
        </n-button>
      </n-flex>
    </n-space>
  </n-card>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { isActiveJobStatus, isFailedJobStatus, type Job } from '@/features/jobs/api/jobs'

const props = withDefaults(
  defineProps<{
    job: Job | null
    cancelling: boolean
    downloading: boolean
    downloadLabel?: string
  }>(),
  { downloadLabel: 'Download result' }
)

defineEmits<{ cancel: []; download: []; open: [] }>()

const active = computed(() => isActiveJobStatus(props.job?.status))
const statusLabel = computed(() => props.job?.status.replaceAll('_', ' ') || '')
const statusType = computed(() => statusValue('success', 'error', 'warning', 'info'))
const progressStatus = computed(() => statusValue('success', 'error', 'warning', 'default'))

function statusValue<T>(success: T, failure: T, cancelled: T, fallback: T): T {
  if (props.job?.status === 'succeeded') return success
  if (props.job && isFailedJobStatus(props.job.status)) return failure
  if (props.job?.status === 'cancelled') return cancelled
  return fallback
}
</script>
