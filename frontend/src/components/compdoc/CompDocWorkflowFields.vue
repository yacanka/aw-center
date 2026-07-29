<template>
  <n-card title="Workflow" size="small">
    <n-alert v-if="!editable" type="info" :show-icon="false">
      Workflow history is audit-controlled. Record status changes from the document workspace.
    </n-alert>
    <n-form-item v-if="editable" path="status_flow" label="Initial status history">
      <n-dynamic-input v-model:value="compdoc.status_flow" :on-create="createStatus">
        <template #create-button-default>Add status and date</template>
        <template #default="{ value }">
          <n-grid responsive="self" item-responsive :cols="48" :x-gap="12" :y-gap="4">
            <n-grid-item span="0:48 700:14">
              <n-select v-model:value="value.status" :options="statusOptions" />
            </n-grid-item>
            <n-grid-item span="0:48 700:10">
              <n-date-picker
                v-model:formatted-value="value.date"
                type="date"
                format="dd.MM.yyyy"
                :first-day-of-week="0"
              />
            </n-grid-item>
            <n-grid-item span="0:48 700:24">
              <n-input v-model:value="value.note" maxlength="500" placeholder="Type note" />
            </n-grid-item>
          </n-grid>
        </template>
      </n-dynamic-input>
    </n-form-item>
    <template v-else>
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
import type { ICompDoc, IStatusFlow } from '@/models/compdocs'
import { statusOptions } from '@/services/compdocCatalog'
import { getTodayEUFormat } from '@/utils/time'

const props = defineProps<{ compdoc: ICompDoc; editable: boolean }>()
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

function createStatus(): IStatusFlow {
  return { date: getTodayEUFormat(), status: '' }
}

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
