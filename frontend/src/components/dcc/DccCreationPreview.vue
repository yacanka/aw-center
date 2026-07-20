<template>
  <n-card v-if="job.status === 'awaiting_confirmation'" title="Review immutable snapshot" embedded>
    <n-space vertical size="large">
      <n-alert type="success" :bordered="false">
        The registered template successfully rendered this exact captured JIRA snapshot.
      </n-alert>
      <n-descriptions :column="2" bordered size="small" label-placement="top">
        <n-descriptions-item label="JIRA task">{{ summary.issue_key }}</n-descriptions-item>
        <n-descriptions-item label="Project">{{ summary.project }}</n-descriptions-item>
        <n-descriptions-item label="Output">{{ summary.output_name }}</n-descriptions-item>
        <n-descriptions-item label="Panel subtasks">
          {{ summary.panel_count ?? 0 }}
        </n-descriptions-item>
        <n-descriptions-item label="Source updated">
          {{ summary.source_updated_at || 'Unavailable' }}
        </n-descriptions-item>
        <n-descriptions-item label="Confirmation expires">
          {{ expirationLabel }}
        </n-descriptions-item>
      </n-descriptions>
      <n-alert v-if="missingFields.length" type="warning" :bordered="false">
        <template #header>Recommended JIRA fields are empty</template>
        {{ missingFields.join(', ') }}. The template rendered, but review these omissions before
        continuing.
      </n-alert>
      <n-alert v-else type="info" :bordered="false">
        No recommended source fields are missing.
      </n-alert>
      <n-space justify="end">
        <n-button type="primary" :loading="confirming" @click="$emit('confirm')">
          Confirm and queue exact snapshot
        </n-button>
      </n-space>
    </n-space>
  </n-card>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { Job } from '@/services/jobs'

const props = defineProps<{ job: Job; confirming: boolean }>()
defineEmits<{ confirm: [] }>()

const summary = computed(() => props.job.result_summary)
const missingFields = computed(() => summary.value.missing_recommended_fields || [])
const expirationLabel = computed(() => {
  if (!props.job.confirmation_expires_at) return 'Unavailable'
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: 'medium',
    timeStyle: 'medium'
  }).format(new Date(props.job.confirmation_expires_at))
})
</script>
