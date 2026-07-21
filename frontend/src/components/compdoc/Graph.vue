<template>
  <n-modal v-model:show="showModal" preset="card" title="Document Summary" class="summary-modal">
    <n-tabs v-model:value="activeTab" :animated="false" type="segment">
      <n-tab-pane name="status" tab="Status" display-directive="if">
        <div class="status-pane">
          <div class="chart-surface chart-surface--status">
            <Doughnut
              v-if="statusTotal"
              :data="statusData"
              :options="statusOptions"
              :plugins="[centerTextPlugin]"
            />
            <n-empty v-else description="No status data" />
          </div>
          <div class="summary-legend">
            <div v-for="row in visibleStatusRows" :key="row.value" class="legend-row">
              <span class="legend-dot" :style="{ background: row.color }" />
              <span>{{ row.label }}</span>
              <strong>{{ row.count }}</strong>
              <n-text depth="3">{{ row.percentage }}%</n-text>
            </div>
          </div>
        </div>
      </n-tab-pane>
      <n-tab-pane name="pending" tab="Pending Days" display-directive="if">
        <div class="chart-surface">
          <Bar :data="pendingData" :options="pendingOptions" />
        </div>
      </n-tab-pane>
      <n-tab-pane name="timeline" tab="Burndown" display-directive="if">
        <div class="chart-surface">
          <Line v-if="hasTimeline" :data="timelineData" :options="timelineOptions" />
          <n-empty v-else description="No schedule or delivery events" />
        </div>
      </n-tab-pane>
    </n-tabs>
  </n-modal>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Bar, Doughnut, Line } from 'vue-chartjs'
import type { ICompDoc } from '@/models/compdocs'
import { useUserStore } from '@/stores/user'
import { resolvePreferredTheme } from '@/services/theme'
import { buildClientCompdocSummary } from '@/services/compdocChartAlgorithms'
import {
  createPendingChartData,
  createStatusChartData,
  createStatusChartRows,
  createTimelineChartData
} from '@/services/compdocChartData'
import {
  centerTextPlugin,
  createStatusChartOptions,
  ensureCompdocChartsRegistered
} from '@/services/compdocChartTheme'
import {
  createPendingChartOptions,
  createTimelineChartOptions
} from '@/services/compdocChartAxisOptions'

ensureCompdocChartsRegistered()
const userStore = useUserStore()
const showModal = ref(false)
const activeTab = ref(localStorage.getItem('summaryActiveTab') || 'status')
const documents = ref<ICompDoc[]>([])
const theme = computed(() => resolvePreferredTheme(userStore.getPreferences))
const summary = computed(() => buildClientCompdocSummary(documents.value))
const statusRows = computed(() => createStatusChartRows(summary.value.statuses))
const visibleStatusRows = computed(() => statusRows.value.filter((row) => row.count > 0))
const statusTotal = computed(() => visibleStatusRows.value.reduce((sum, row) => sum + row.count, 0))
const statusData = computed(() => createStatusChartData(statusRows.value))
const statusOptions = computed(() => createStatusChartOptions(theme.value))
const pendingData = computed(() => createPendingChartData(summary.value.pendingDays))
const pendingOptions = computed(() => createPendingChartOptions(theme.value))
const timelineData = computed(() =>
  createTimelineChartData(summary.value.timeline, documents.value.length)
)
const timelineOptions = computed(() =>
  createTimelineChartOptions(
    theme.value,
    summary.value.timeline.today[0]?.x,
    documents.value.length
  )
)
const hasTimeline = computed(
  () => summary.value.timeline.scheduled.length > 0 || summary.value.timeline.actual.length > 1
)

function openModal(rows: ICompDoc[]) {
  documents.value = [...rows]
  showModal.value = true
}

watch(activeTab, (tab) => localStorage.setItem('summaryActiveTab', tab))

defineExpose({ openModal })
</script>

<style scoped>
:global(.summary-modal) {
  width: min(900px, calc(100vw - 32px));
}

.chart-surface {
  position: relative;
  height: 450px;
  min-width: 0;
  padding-top: 16px;
}

.status-pane {
  display: grid;
  grid-template-columns: minmax(300px, 1fr) minmax(260px, 0.75fr);
  gap: 28px;
  align-items: center;
}

.chart-surface--status {
  height: 420px;
}

.summary-legend {
  display: grid;
  gap: 12px;
}

.legend-row {
  display: grid;
  grid-template-columns: 10px minmax(150px, 1fr) 36px 44px;
  gap: 9px;
  align-items: center;
}

.legend-dot {
  width: 9px;
  height: 9px;
  border-radius: 50%;
}

@media (max-width: 680px) {
  .status-pane {
    grid-template-columns: 1fr;
  }

  .chart-surface--status {
    height: 330px;
  }
}
</style>
