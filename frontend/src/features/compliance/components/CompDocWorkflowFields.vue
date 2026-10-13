<template>
  <n-card title="Workflow and dates" size="small">
    <n-alert type="info" :show-icon="false">
      Workflow history is audit-controlled. Record status changes from the document workspace.
    </n-alert>
    <n-descriptions label-placement="top" :column="isNarrow ? 1 : 2" bordered size="small">
      <n-descriptions-item label="Current status">
        <n-tag :color="statusColor" :bordered="false" round>{{
          displayDocument.status_label || statusLabel(compdoc.status)
        }}</n-tag>
      </n-descriptions-item>
      <n-descriptions-item label="UBM target">
        <span v-if="readonly">{{
          compdoc.ubm_target_date ? formatTurkishDate(compdoc.ubm_target_date) : 'Not recorded'
        }}</span>
        <n-date-picker
          v-else
          v-model:formatted-value="compdoc.ubm_target_date"
          type="date"
          format="dd.MM.yyyy"
          value-format="yyyy-MM-dd"
          clearable
        />
      </n-descriptions-item>
      <n-descriptions-item label="UBM revised target">
        <span v-if="readonly">{{
          compdoc.ubm_revised_target_date
            ? formatTurkishDate(compdoc.ubm_revised_target_date)
            : 'Not recorded'
        }}</span>
        <n-date-picker
          v-else
          v-model:formatted-value="compdoc.ubm_revised_target_date"
          type="date"
          format="dd.MM.yyyy"
          value-format="yyyy-MM-dd"
          clearable
        />
      </n-descriptions-item>
      <n-descriptions-item label="UBM delivery">
        <span v-if="readonly">{{
          compdoc.ubm_delivery_date ? formatTurkishDate(compdoc.ubm_delivery_date) : 'Not recorded'
        }}</span>
        <n-date-picker
          v-else
          v-model:formatted-value="compdoc.ubm_delivery_date"
          type="date"
          format="dd.MM.yyyy"
          value-format="yyyy-MM-dd"
          clearable
        />
      </n-descriptions-item>
    </n-descriptions>
    <n-text depth="3" class="workflow-note">
      The complete transition trail is available in the document workspace Activity tab.
    </n-text>
  </n-card>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { formatTurkishDate } from '@/shared/utils/time'
import { withCompdocDisplayStatus } from '@/features/compliance/api/compdocStatus'
import { statusColors } from '@/features/compliance/api/compdocCatalog'
import type { ICompDoc } from '@/features/compliance/models/compdocs'
import { humanizeCompdocStatus } from '@/features/compliance/api/compdocWorkspace'
import { useMediaQuery } from '@/shared/composables/mediaQuery'

const props = defineProps<{ compdoc: ICompDoc; readonly: boolean }>()
const displayDocument = computed(() => withCompdocDisplayStatus(props.compdoc))
const statusColor = computed(() => {
  const colors =
    statusColors[
      displayDocument.value.status_label === 'In Design (date missing)'
        ? 'missing_target'
        : displayDocument.value.status
    ]
  return colors ? { color: colors.color25, textColor: colors.color } : undefined
})
const isNarrow = useMediaQuery('(max-width: 640px)')

function statusLabel(status: string): string {
  return humanizeCompdocStatus(status)
}
</script>

<style scoped>
.workflow-note {
  display: block;
  margin-top: 10px;
}
</style>
