<template>
  <n-tabs v-model:value="activeProject" @update:value="loadProject">
    <n-tab-pane
      v-for="project in projectOptions"
      :key="project.value"
      :name="project.value"
      :tab="project.label"
      :disabled="project.disabled"
    />
  </n-tabs>

  <n-alert v-if="error" type="error" title="Dashboard could not be loaded" closable>
    {{ error }}
  </n-alert>

  <n-spin :show="loading">
    <n-empty v-if="!summary && !loading" description="No dashboard data is available." />
    <template v-else-if="summary">
      <n-grid cols="1 s:3" responsive="screen" :x-gap="12" :y-gap="12" class="metrics">
        <n-gi>
          <n-statistic label="Active documents" :value="summary.total" />
        </n-gi>
        <n-gi>
          <n-statistic label="Overdue actions" :value="summary.overdue" />
        </n-gi>
        <n-gi>
          <n-statistic label="Archived documents" :value="summary.archived" />
        </n-gi>
      </n-grid>
      <CompDocStatusDashboard :counts="summary.status_counts" />
    </template>
  </n-spin>
</template>

<script setup lang="ts">
import { useCompdocDashboard } from '@/features/compliance/composables/dashboard'
import CompDocStatusDashboard from './CompDocStatusDashboard.vue'

const { activeProject, error, loading, loadProject, projectOptions, summary } =
  useCompdocDashboard()
</script>

<style scoped>
.metrics {
  margin: 4px 0 16px;
}

.metrics :deep(.n-statistic) {
  padding: 16px;
  border-radius: 10px;
  background: rgba(100, 116, 139, 0.08);
}
</style>
