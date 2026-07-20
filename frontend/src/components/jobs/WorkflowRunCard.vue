<template>
  <n-list-item>
    <n-thing :title="workflow.title" :description="workflow.input_name">
      <template #header-extra>
        <n-tag :type="statusType(workflow.status)">{{ statusLabel(workflow.status) }}</n-tag>
      </template>
      <n-space vertical size="small">
        <n-progress
          type="line"
          :percentage="workflow.progress"
          :status="progressStatus(workflow.status)"
          indicator-placement="inside"
        />
        <n-text>{{ workflow.message }}</n-text>
        <n-space v-for="step in workflow.steps" :key="step.sequence" align="center">
          <n-tag size="small" round>{{ step.sequence }}</n-tag>
          <n-text :depth="step.job ? 1 : 3">{{ step.label }}</n-text>
          <n-tag size="small" :type="step.job ? statusType(step.job.status) : 'default'">
            {{ step.job ? statusLabel(step.job.status) : 'pending' }}
          </n-tag>
          <n-button v-if="step.job" text type="primary" @click="$emit('open-job', step.job.id)">
            Open
          </n-button>
        </n-space>
        <n-alert v-if="workflow.recovery_hint" type="warning" :bordered="false">
          {{ workflow.recovery_hint }}
        </n-alert>
        <n-text depth="3">Started {{ formatDate(workflow.created_at) }}</n-text>
      </n-space>
      <template #action>
        <n-button
          v-if="workflow.can_cancel"
          size="small"
          type="warning"
          :loading="cancelling"
          @click="$emit('cancel', workflow)"
        >
          Cancel workflow
        </n-button>
      </template>
    </n-thing>
  </n-list-item>
</template>

<script setup lang="ts">
import type { JobStatus } from '@/services/jobs'
import type { WorkflowRun } from '@/services/workflows'

defineProps<{ workflow: WorkflowRun; cancelling: boolean }>()
defineEmits<{ cancel: [workflow: WorkflowRun]; 'open-job': [jobId: string] }>()

function formatDate(value: string): string {
  return new Intl.DateTimeFormat(undefined, { dateStyle: 'short', timeStyle: 'short' }).format(
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
</script>
