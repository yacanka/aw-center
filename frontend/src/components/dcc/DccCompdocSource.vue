<template>
  <n-alert type="success" :bordered="false">
    <template #header>Compliance Documents linked</template>
    {{ selection.documentIds.length }} records from {{ selection.project }} will be captured with
    their exact history versions and appended to the generated DCC as a fingerprinted traceability
    register.
    <template #action>
      <n-button text @click="$emit('remove')">Remove selection</n-button>
    </template>
  </n-alert>
</template>

<script setup lang="ts">
import type { DccCompdocSelection } from '@/services/dccJobs'

defineProps<{ selection: DccCompdocSelection }>()
defineEmits<{ remove: [] }>()
</script>
