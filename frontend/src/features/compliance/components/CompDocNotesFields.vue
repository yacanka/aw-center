<template>
  <n-card title="Notes" size="small">
    <n-form-item path="notes" label="Notes">
      <n-input
        v-model:value="compdoc.notes"
        type="textarea"
        maxlength="5000"
        show-count
        :readonly="readonly"
        :status="original.notes === compdoc.notes ? '' : 'warning'"
      />
    </n-form-item>
    <n-form-item v-if="showChangeReason" path="change_reason" label="Change reason (optional)">
      <n-input
        v-model:value="compdoc.change_reason"
        maxlength="100"
        show-count
        placeholder="Optionally explain why this record is changing"
      />
    </n-form-item>
  </n-card>
</template>

<script setup lang="ts">
import type { ICompDoc } from '@/features/compliance/models/compdocs'

defineProps<{
  compdoc: ICompDoc
  original: ICompDoc
  readonly: boolean
  showChangeReason: boolean
}>()
</script>
