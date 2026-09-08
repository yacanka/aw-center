<template>
  <n-card title="Workflow" size="small">
    <n-alert type="info" :show-icon="false">
      Workflow history is audit-controlled. Record status changes from the document workspace.
    </n-alert>
    <n-descriptions label-placement="top" :column="3" bordered size="small">
      <n-descriptions-item label="Current status">
        <n-tag type="success" round>{{ statusLabel(compdoc.status) }}</n-tag>
      </n-descriptions-item>
      <n-descriptions-item label="UBM target">
        {{ compdoc.ubm_target_date || 'Not recorded' }}
      </n-descriptions-item>
      <n-descriptions-item label="UBM delivery">
        {{ compdoc.ubm_delivery_date || 'Not recorded' }}
      </n-descriptions-item>
    </n-descriptions>
    <n-text depth="3" class="workflow-note">
      The complete transition trail is available in the document workspace Activity tab.
    </n-text>
  </n-card>
</template>

<script setup lang="ts">
import type { ICompDoc } from '@/features/compliance/models/compdocs'
import { statusOptions } from '@/features/compliance/api/compdocCatalog'

defineProps<{ compdoc: ICompDoc }>()

function statusLabel(status: string): string {
  return statusOptions.find((option) => option.value === status)?.label || status || 'Unknown'
}
</script>

<style scoped>
.workflow-note {
  display: block;
  margin-top: 10px;
}
</style>
