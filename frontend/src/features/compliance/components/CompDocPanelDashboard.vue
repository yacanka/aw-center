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
import { computed } from 'vue'
import { humanizeCompdocStatus } from '@/features/compliance/api/compdocWorkspace'
import type { CompdocOption } from '@/features/compliance/api/compdocCatalog'
import type { DataTableColumns } from 'naive-ui'
import type { DashboardPanel } from '@/features/compliance/models/compdocDashboard'

const props = defineProps<{
  statuses?: CompdocOption[]
  loading: boolean
  panels: DashboardPanel[]
  selectedPanel?: string
}>()
const emit = defineEmits<{ select: [panel: DashboardPanel] }>()

const columns = computed<DataTableColumns<DashboardPanel>>(() => {
  const statuses = new Map((props.statuses || []).map((item) => [item.value, item.label]))
  props.panels.forEach((panel) =>
    Object.keys(panel.analytics.chart_status_counts).forEach((value) => {
      if (!statuses.has(value)) statuses.set(value, humanizeCompdocStatus(value))
    })
  )
  return [
    { title: 'Panel', key: 'panel', minWidth: 140, ellipsis: { tooltip: true } },
    { title: 'ATA', key: 'ata', width: 80 },
    ...[...statuses].map(([value, label]) => statusColumn(label, value)),
    {
      title: 'Total',
      key: 'total',
      width: 64,
      align: 'center',
      render: (row) => row.analytics.total
    }
  ]
})

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
