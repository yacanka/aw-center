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
            <n-descriptions-item v-if="job.source_job" label="Workflow source">
              <n-button text type="primary" @click="$emit('open-job', job.source_job)">
                {{ job.source_job }}
              </n-button>
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
          <n-card
            v-if="job.result_summary.type === 'dcc_preview'"
            title="DCC snapshot review"
            size="small"
          >
            <n-space vertical>
              <n-descriptions :column="2" bordered size="small">
                <n-descriptions-item label="JIRA task">
                  {{ job.result_summary.issue_key }}
                </n-descriptions-item>
                <n-descriptions-item label="Project">
                  {{ job.result_summary.project }}
                </n-descriptions-item>
                <n-descriptions-item label="Output">
                  {{ job.result_summary.output_name }}
                </n-descriptions-item>
                <n-descriptions-item label="Panels">
                  {{ job.result_summary.panel_count ?? 0 }}
                </n-descriptions-item>
              </n-descriptions>
              <n-alert type="warning" :bordered="false">
                This immutable source has not been exposed to a worker yet.
              </n-alert>
              <router-link :to="{ name: 'dcc', query: { dcc_job: job.id } }">
                Review and confirm in DCC Creator
              </router-link>
            </n-space>
          </n-card>
          <JiraIssueDraftPanel :job="job" />
          <n-card v-if="job.handoffs.length" title="Suggested next step" size="small">
            <n-space vertical>
              <n-alert type="info" :bordered="false">
                Reuse this verified private output without downloading and uploading it again.
              </n-alert>
              <n-space
                v-for="handoff in job.handoffs"
                :key="handoff.id"
                justify="space-between"
                align="center"
              >
                <div>
                  <n-text strong>{{ handoff.label }}</n-text>
                  <br />
                  <n-text depth="3">{{ handoff.description }}</n-text>
                </div>
                <n-button
                  type="primary"
                  secondary
                  :loading="handoffLoading"
                  @click="$emit('handoff', job, handoff)"
                >
                  Start
                </n-button>
              </n-space>
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
import JiraIssueDraftPanel from '@/components/jobs/JiraIssueDraftPanel.vue'
import type { Job, JobHandoff, JobStatus } from '@/services/jobs'

defineProps<{ show: boolean; loading: boolean; handoffLoading: boolean; job: Job | null }>()
defineEmits<{
  'update:show': [show: boolean]
  handoff: [job: Job, handoff: JobHandoff]
  'open-job': [jobId: string]
}>()

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
