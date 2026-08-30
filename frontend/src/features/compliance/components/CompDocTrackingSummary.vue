<script setup lang="ts">
import type { DashboardTrackingSummary } from '@/features/compliance/models/compdocDashboard'

defineProps<{ tracking: DashboardTrackingSummary }>()
const metrics: Array<{
  key: keyof DashboardTrackingSummary
  label: string
  tone: 'default' | 'success' | 'warning' | 'error'
}> = [
  { key: 'configured_count', label: 'Tracked', tone: 'default' },
  { key: 'notification_enabled_count', label: 'Alerts enabled', tone: 'success' },
  { key: 'revision_available_count', label: 'New revisions', tone: 'warning' },
  { key: 'delivery_failure_count', label: 'Delivery issues', tone: 'error' }
]
</script>

<template>
  <n-card title="Tracking pulse" size="small" class="tracking-summary">
    <div class="tracking-metrics">
      <div v-for="metric in metrics" :key="metric.key" class="tracking-metric">
        <n-text depth="3">{{ metric.label }}</n-text>
        <n-text :type="metric.tone" class="tracking-value">
          {{ tracking[metric.key] }}
        </n-text>
      </div>
    </div>
    <n-alert
      v-if="tracking.revision_available_count || tracking.delivery_failure_count"
      type="warning"
      :bordered="false"
    >
      Review new DocProof revisions and unresolved mail delivery attempts in each document’s
      Tracking & alerts workspace.
    </n-alert>
  </n-card>
</template>

<style scoped>
.tracking-summary {
  margin-bottom: 16px;
}

.tracking-metrics {
  display: grid;
  grid-template-columns: repeat(4, minmax(110px, 1fr));
  gap: 12px;
  margin-bottom: 12px;
}

.tracking-metric {
  display: grid;
  gap: 4px;
  padding: 12px;
  border-radius: 10px;
  background: rgba(100, 116, 139, 0.08);
}

.tracking-value {
  font-size: 24px;
  font-weight: 700;
}

@media (max-width: 720px) {
  .tracking-metrics {
    grid-template-columns: repeat(2, 1fr);
  }
}
</style>
