<template>
  <n-card title="Panel breakdown" class="dashboard-card">
    <n-data-table
      size="small"
      striped
      :loading="loading"
      :columns="columns"
      :data="panels"
      :scroll-x="520"
      :max-height="250"
      :row-key="(row: DashboardPanel) => row.id"
      :row-props="rowProps"
    />
    <n-text depth="3" class="panel-hint">
      All project panels. Double-click a row or press Enter to focus all charts and risk priorities.
      Repeat to show all panels.
    </n-text>
  </n-card>
</template>

<script setup lang="ts">
import type { DataTableColumns } from 'naive-ui'
import type { DashboardPanel } from '@/features/compliance/models/compdocDashboard'

const props = defineProps<{
  loading: boolean
  panels: DashboardPanel[]
  selectedPanel?: string
}>()
const emit = defineEmits<{ select: [panel: DashboardPanel] }>()

const columns: DataTableColumns<DashboardPanel> = [
  { title: 'Panel', key: 'panel', minWidth: 140, ellipsis: { tooltip: true } },
  { title: 'ATA', key: 'ata', width: 80 },
  statusColumn('To issue', 'to_be_issued', true),
  statusColumn('Update', 'to_be_updated'),
  statusColumn('Re-submit', 'to_be_re-submitted'),
  statusColumn('AW review', 'airworthiness_review'),
  statusColumn('Authority', 'authority_review'),
  statusColumn('Approved', 'authority_approved'),
  statusColumn('Unknown', 'unknown'),
  { title: 'Total', key: 'total', width: 64, align: 'center', render: (row) => row.analytics.total }
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
  const value = panel.analytics.chart_status_counts[status]
  return typeof value === 'number' ? value : 0
}

function rowProps(panel: DashboardPanel) {
  return {
    class: props.selectedPanel === panel.id ? 'selected-panel' : '',
    tabindex: 0,
    'aria-label': `Focus ${panel.panel}${panel.ata ? ` · ${panel.ata}` : ''}`,
    'aria-selected': props.selectedPanel === panel.id,
    onDblclick: () => emit('select', panel),
    onKeydown: (event: KeyboardEvent) => {
      if (event.key !== 'Enter' && event.key !== ' ') return
      event.preventDefault()
      emit('select', panel)
    }
  }
}
</script>

<style scoped>
.dashboard-card {
  width: 100%;
  min-width: 0;
}

.panel-hint {
  display: block;
  margin-top: 12px;
  font-size: 12px;
}

:deep(tbody tr) {
  cursor: pointer;
}

:deep(tbody tr:focus-visible) {
  outline: 2px solid currentColor;
  outline-offset: -2px;
}

:deep(.selected-panel td) {
  background: rgba(24, 160, 88, 0.12) !important;
}
</style>
