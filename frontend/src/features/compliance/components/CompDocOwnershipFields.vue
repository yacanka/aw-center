<template>
  <n-card title="Ownership" size="small">
    <n-form-item path="responsible" label="Legacy / external responsible">
      <n-input
        v-model:value="compdoc.responsible"
        maxlength="256"
        :readonly="readonly"
        :status="original.responsible === compdoc.responsible ? '' : 'warning'"
        @keydown.enter.prevent
      />
    </n-form-item>
    <n-text depth="3">
      AW Center owner, team, and next-action date are managed in the document workspace.
    </n-text>
  </n-card>
</template>

<script setup lang="ts">
import type { ICompDoc } from '@/features/compliance/models/compdocs'

defineProps<{
  compdoc: ICompDoc
  original: ICompDoc
  readonly: boolean
}>()
</script>
