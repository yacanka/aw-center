<template>
  <n-card title="Workflow" size="small">
    <n-alert v-if="!editable" type="info" :show-icon="false">
      Existing workflow history is read-only. Record a new transition from the document workspace.
    </n-alert>
    <n-form-item path="status_flow" label="Status history">
      <n-dynamic-input
        v-model:value="compdoc.status_flow"
        :disabled="!editable"
        :on-create="createStatus"
      >
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
  </n-card>
</template>

<script setup lang="ts">
import type { ICompDoc, IStatusFlow } from '@/models/compdocs'
import { statusOptions } from '@/services/compdocCatalog'
import { getTodayEUFormat } from '@/utils/time'

defineProps<{ compdoc: ICompDoc; editable: boolean }>()

function createStatus(): IStatusFlow {
  return { date: getTodayEUFormat(), status: '' }
}
</script>
