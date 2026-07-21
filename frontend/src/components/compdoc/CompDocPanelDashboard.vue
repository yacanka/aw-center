<template>
  <n-card title="Panel breakdown" class="dashboard-card">
    <n-scrollbar style="max-height: 250px">
      <n-data-table
        size="small"
        striped
        :loading="loading"
        :columns="columns"
        :data="panels"
        :row-key="(row: DashboardPanel) => row.panel"
        :row-props="rowProps"
      />
    </n-scrollbar>
    <n-text depth="3">Double-click a panel to focus the status chart.</n-text>
  </n-card>
</template>

<script setup lang="ts">
import type { DataTableColumns } from 'naive-ui'
import type { DashboardPanel } from '@/models/compdocDashboard'

const props = defineProps<{
  loading: boolean
  panels: DashboardPanel[]
  selectedPanel?: string
}>()
const emit = defineEmits<{ select: [panel: DashboardPanel] }>()

const columns: DataTableColumns<DashboardPanel> = [
  { title: 'Panel', key: 'panel', minWidth: 140, ellipsis: { tooltip: true } },
  statusColumn('To issue', 'to_be_issued', true),
  statusColumn('Update', 'to_be_updated'),
  statusColumn('Re-submit', 'to_be_re-submitted'),
  statusColumn('AW review', 'airworthiness_review'),
  statusColumn('Authority', 'authority_review'),
  statusColumn('Approved', 'authority_approved'),
  { title: 'Total', key: 'total', width: 64, align: 'center' }
]

function statusColumn(
  title: string,
  key: string,
  includeDelayed = false
): DataTableColumns<DashboardPanel>[number] {
  return {
    title,
    key,
    width: 88,
    align: 'center',
    render(row) {
      const count = readCount(row, key) + (includeDelayed ? readCount(row, 'delayed') : 0)
      return count || null
    }
  }
}

function readCount(panel: DashboardPanel, status: string): number {
  const value = panel[status]
  return typeof value === 'number' ? value : 0
}

function rowProps(panel: DashboardPanel) {
  return {
    class: props.selectedPanel === panel.panel ? 'selected-panel' : '',
    onDblclick: () => emit('select', panel)
  }
}
</script>

<style scoped>
.dashboard-card {
  width: 100%;
}

:deep(.selected-panel td) {
  background: rgba(24, 160, 88, 0.12) !important;
}
</style>
