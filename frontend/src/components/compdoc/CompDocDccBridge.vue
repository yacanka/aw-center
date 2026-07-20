<template>
  <n-button
    v-if="selectedIds.length"
    type="primary"
    secondary
    :disabled="selectedIds.length > MAX_SELECTION"
    @click="launchDccCreator"
  >
    Create DCC with {{ selectedIds.length }} selected
  </n-button>
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router'

const MAX_SELECTION = 50
const props = defineProps<{ project: string; selectedIds: string[] }>()
const router = useRouter()

function launchDccCreator(): void {
  void router.push({
    name: 'dcc',
    query: {
      compdoc_project: props.project,
      compdocs: props.selectedIds.join(',')
    }
  })
}
</script>
