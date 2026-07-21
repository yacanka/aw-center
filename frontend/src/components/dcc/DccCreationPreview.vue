<template>
  <n-card v-if="job.status === 'awaiting_confirmation'" title="Review immutable snapshot" embedded>
    <n-space vertical size="large">
      <n-alert type="success" :bordered="false">
        The registered template successfully rendered this exact captured JIRA snapshot.
      </n-alert>
      <n-card title="DCC readiness" size="small">
        <n-space vertical>
          <n-progress
            type="line"
            :percentage="readinessScore"
            :status="readinessProgressStatus"
            indicator-placement="inside"
            processing
          />
          <n-alert :type="readinessAlertType" :bordered="false">
            <template #header>{{ readinessTitle }}</template>
            Every warning below must be reviewed before this immutable snapshot can be queued.
          </n-alert>
          <n-list bordered>
            <n-list-item v-for="check in readinessChecks" :key="check.code">
              <n-space vertical size="small">
                <n-space align="center">
                  <n-tag size="small" :type="checkTagType(check.status)">
                    {{ check.status }}
                  </n-tag>
                  <n-text strong>{{ check.title }}</n-text>
                </n-space>
                <n-text>{{ check.detail }}</n-text>
                <n-text depth="3">Next step: {{ check.recovery_hint }}</n-text>
              </n-space>
            </n-list-item>
          </n-list>
        </n-space>
      </n-card>
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
      <n-alert v-if="requiresAcknowledgement" type="warning" :bordered="false">
        <n-space align="center">
          <n-switch v-model:value="warningsAcknowledged" />
          <n-text>I reviewed every readiness warning and accept this exact snapshot.</n-text>
        </n-space>
      </n-alert>
      <n-space justify="end">
        <n-button
          type="primary"
          :loading="confirming"
          :disabled="requiresAcknowledgement && !warningsAcknowledged"
          @click="confirmSnapshot"
        >
          Confirm and queue exact snapshot
        </n-button>
      </n-space>
    </n-space>
  </n-card>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { Job } from '@/services/jobs'
import type { DccReadinessCheck } from '@/services/jobSummaries'

const props = defineProps<{ job: Job; confirming: boolean }>()
const emit = defineEmits<{
  confirm: [warningCodes: string[]]
}>()

const summary = computed(() => props.job.result_summary)
const warningsAcknowledged = ref(false)
const readinessScore = computed(() => summary.value.readiness_score ?? 0)
const readinessChecks = computed(() => summary.value.readiness_checks || [])
const warningCodes = computed(() => summary.value.readiness_warning_codes || [])
const requiresAcknowledgement = computed(
  () => summary.value.requires_readiness_acknowledgement === true
)
const readinessTitle = computed(() =>
  requiresAcknowledgement.value ? 'Human review required' : 'Ready for confirmation'
)
const readinessAlertType = computed(() => (requiresAcknowledgement.value ? 'warning' : 'success'))
const readinessProgressStatus = computed(() =>
  requiresAcknowledgement.value ? 'warning' : 'success'
)
const expirationLabel = computed(() => {
  if (!props.job.confirmation_expires_at) return 'Unavailable'
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: 'medium',
    timeStyle: 'medium'
  }).format(new Date(props.job.confirmation_expires_at))
})

watch(
  () => props.job.id,
  () => (warningsAcknowledged.value = false)
)

function confirmSnapshot(): void {
  if (requiresAcknowledgement.value && !warningsAcknowledged.value) return
  emit('confirm', requiresAcknowledgement.value ? warningCodes.value : [])
}

function checkTagType(status: DccReadinessCheck['status']): 'success' | 'warning' | 'info' {
  if (status === 'success') return 'success'
  return status === 'warning' ? 'warning' : 'info'
}
</script>
