<template>
  <n-card title="Workflow" size="small">
    <n-alert type="info" :show-icon="false">
      Workflow history is audit-controlled. Record status changes from the document workspace.
    </n-alert>
    <template>
      <n-flex v-if="workflowEntries.length" align="center" class="workflow-summary">
        <n-text depth="3">Current status</n-text>
        <n-tag type="success" round>{{ statusLabel(compdoc.status) }}</n-tag>
        <n-text depth="3">{{ workflowEntries.length }} recorded transitions</n-text>
      </n-flex>
      <n-timeline v-if="workflowEntries.length" class="workflow-timeline">
        <n-timeline-item
          v-for="entry in workflowEntries"
          :key="`${entry.originalIndex}-${entry.date}-${entry.status}`"
          :type="entry.isCurrent ? 'success' : 'default'"
          :title="statusLabel(entry.status)"
          :content="entry.note || 'No reason was recorded for this transition.'"
          :time="entry.date || 'Date not recorded'"
        />
      </n-timeline>
      <n-empty
        v-else
        class="workflow-empty"
        size="small"
        description="No workflow transition has been recorded yet."
      />
    </template>
  </n-card>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { ICompDoc } from '@/features/compliance/models/compdocs'
import { statusOptions } from '@/features/compliance/api/compdocCatalog'

const props = defineProps<{ compdoc: ICompDoc }>()
const workflowEntries = computed(() => {
  const flow = props.compdoc.status_flow || []
  return flow
    .map((entry, originalIndex) => ({
      ...entry,
      originalIndex,
      isCurrent: originalIndex === flow.length - 1
    }))
    .reverse()
})

function statusLabel(status: string): string {
  return statusOptions.find((option) => option.value === status)?.label || status || 'Unknown'
}
</script>

<style scoped>
.workflow-summary {
  margin: 14px 0 18px;
}

.workflow-timeline {
  padding: 4px 8px;
}

.workflow-empty {
  padding: 24px 0 12px;
}
</style>
