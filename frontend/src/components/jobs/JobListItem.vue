<template>
  <n-list-item>
    <n-thing :title="job.title" :description="job.input_name">
      <template #header-extra>
        <n-tag :type="statusType(job.status)">{{ statusLabel(job.status) }}</n-tag>
      </template>
      <n-space vertical size="small">
        <n-progress
          type="line"
          :percentage="job.progress"
          :status="progressStatus(job.status)"
          :indicator-placement="'inside'"
        />
        <n-text>{{ job.message || 'Waiting for worker.' }}</n-text>
        <n-text v-if="job.error_code" type="error">Code: {{ job.error_code }}</n-text>
        <n-alert v-if="job.recovery_hint" type="info" :bordered="false">
          {{ job.recovery_hint }}
        </n-alert>
        <n-alert
          v-if="job.result_summary.type === 'document_analysis'"
          type="info"
          :bordered="false"
        >
          {{ job.result_summary.passed }}/{{ job.result_summary.total }} strong checks · overall
          {{ scorePercentage(job.result_summary.overall_score) }}%
        </n-alert>
        <n-space size="large">
          <n-text depth="3">Attempt {{ job.attempt }}/{{ job.max_attempts }}</n-text>
          <n-text depth="3">Queued {{ formatDate(job.created_at) }}</n-text>
          <n-text v-if="job.completed_at" depth="3">
            Completed {{ formatDate(job.completed_at) }}
          </n-text>
        </n-space>
      </n-space>
      <template #action>
        <n-space>
          <n-button size="small" @click="$emit('details', job)">Details</n-button>
          <n-button
            v-if="job.can_cancel"
            size="small"
            type="warning"
            :loading="active"
            @click="$emit('cancel', job)"
          >
            Cancel
          </n-button>
          <n-button
            v-if="job.can_retry"
            size="small"
            :loading="active"
            @click="$emit('retry', job)"
          >
            Retry
          </n-button>
          <n-button
            v-if="job.download_url"
            size="small"
            type="primary"
            @click="$emit('download', job)"
          >
            Download {{ job.output_name }}
          </n-button>
        </n-space>
      </template>
    </n-thing>
  </n-list-item>
</template>

<script setup lang="ts">
import type { Job, JobStatus } from '@/services/jobs'

defineProps<{ job: Job; active: boolean }>()
defineEmits<{
  details: [job: Job]
  cancel: [job: Job]
  retry: [job: Job]
  download: [job: Job]
}>()

function formatDate(value: string): string {
  return new Intl.DateTimeFormat(undefined, { dateStyle: 'short', timeStyle: 'medium' }).format(
    new Date(value)
  )
}

function statusLabel(status: JobStatus): string {
  return status.replaceAll('_', ' ')
}

function statusType(status: JobStatus): 'default' | 'info' | 'success' | 'warning' | 'error' {
  if (status === 'succeeded') return 'success'
  if (status === 'failed') return 'error'
  if (status.includes('cancel')) return 'warning'
  return status === 'running' ? 'info' : 'default'
}

function progressStatus(status: JobStatus): 'default' | 'success' | 'error' | 'warning' {
  if (status === 'succeeded') return 'success'
  if (status === 'failed') return 'error'
  return status.includes('cancel') ? 'warning' : 'default'
}

function scorePercentage(score: number | undefined): number {
  return Math.round((score || 0) * 100)
}
</script>
