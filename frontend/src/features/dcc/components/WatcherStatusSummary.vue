<script setup lang="ts">
import { computed } from 'vue'
import type { WatcherStatus } from '../api/watcher'
const props = defineProps<{ status?: WatcherStatus; error?: string; busy?: boolean }>()
const completedCount = computed(
  () => props.status?.subtasks.filter((task) => task.completed).length || 0
)
</script>
<template>
  <n-space vertical :size="6">
    <n-flex v-if="busy" align="center" :size="8"
      ><n-spin :size="16" /><n-text>Checking JIRA…</n-text></n-flex
    >
    <template v-else-if="error"
      ><n-text type="error">Check failed</n-text
      ><n-text class="status-error">{{ error }}</n-text></template
    >
    <template v-else-if="status">
      <n-flex align="center" :size="8">
        <n-tag :type="status.completed ? 'success' : 'warning'" :bordered="false" size="small">{{
          status.completed ? 'Completed' : 'Progressing'
        }}</n-tag>
        <n-text>{{ status.status || 'Unknown status' }}</n-text>
      </n-flex>
      <n-text v-if="status.subtasks.length"
        >{{ completedCount }} of {{ status.subtasks.length }} subtasks complete</n-text
      >
      <n-text v-else>No subtasks</n-text>
    </template>
    <template v-else
      ><n-text>Not checked yet</n-text
      ><n-text depth="2">Open details to load JIRA status.</n-text></template
    >
  </n-space>
</template>
<style scoped>
.status-error {
  overflow-wrap: anywhere;
}
</style>
