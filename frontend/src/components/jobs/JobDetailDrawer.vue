<template>
  <n-drawer :show="show" :width="560" @update:show="$emit('update:show', $event)">
    <n-drawer-content :title="job?.title || 'Job details'" closable>
      <n-spin :show="loading">
        <n-space v-if="job" vertical size="large">
          <n-descriptions :column="2" bordered size="small">
            <n-descriptions-item label="Status">{{ job.status }}</n-descriptions-item>
            <n-descriptions-item label="Attempt">
              {{ job.attempt }}/{{ job.max_attempts }}
            </n-descriptions-item>
            <n-descriptions-item label="Job ID">{{ job.id }}</n-descriptions-item>
            <n-descriptions-item label="Request ID">
              {{ job.request_id || 'Unavailable' }}
            </n-descriptions-item>
          </n-descriptions>
          <n-card
            v-if="job.result_summary.type === 'document_analysis'"
            title="Document analysis summary"
            size="small"
          >
            <n-space vertical>
              <div v-for="check in job.result_summary.checks || []" :key="check.id">
                <n-text>{{ check.title }}</n-text>
                <n-progress
                  type="line"
                  :percentage="Math.round(check.score * 100)"
                  :status="check.status"
                  indicator-placement="inside"
                />
              </div>
            </n-space>
          </n-card>
          <n-timeline>
            <n-timeline-item
              v-for="event in job.events || []"
              :key="event.id"
              :type="eventType(event.status)"
              :title="event.status.replaceAll('_', ' ')"
              :content="event.message"
              :time="formatDate(event.created_at)"
            />
          </n-timeline>
        </n-space>
      </n-spin>
    </n-drawer-content>
  </n-drawer>
</template>

<script setup lang="ts">
import type { Job, JobStatus } from '@/services/jobs'

defineProps<{ show: boolean; loading: boolean; job: Job | null }>()
defineEmits<{ 'update:show': [show: boolean] }>()

function eventType(status: JobStatus): 'default' | 'success' | 'error' | 'warning' | 'info' {
  if (status === 'succeeded') return 'success'
  if (status === 'failed') return 'error'
  if (status.includes('cancel')) return 'warning'
  return status === 'running' ? 'info' : 'default'
}

function formatDate(value: string): string {
  return new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'medium' }).format(
    new Date(value)
  )
}
</script>
