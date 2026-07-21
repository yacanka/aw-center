<template>
  <div class="timeline-stack">
    <n-card class="chart-card" :bordered="false">
      <template #header>
        <div>
          <div class="card-title">Schedule and delivery trend</div>
          <n-text depth="3" class="card-subtitle">Remaining documents over time</n-text>
        </div>
      </template>
      <div class="timeline-surface">
        <Line v-if="hasTimeline" :data="chartData" :options="chartOptions" />
        <n-empty v-else description="No schedule or delivery events" size="small" />
      </div>
    </n-card>

    <n-card class="metric-card" title="Flow performance" :bordered="false">
      <div v-for="item in metrics" :key="item.key" class="metric">
        <n-flex justify="space-between" align="center">
          <span>{{ item.label }}</span>
          <strong>{{ item.value.percentage }}%</strong>
        </n-flex>
        <n-progress
          type="line"
          :percentage="item.value.percentage"
          :show-indicator="false"
          :height="10"
          :border-radius="8"
          :color="item.color"
          rail-color="rgba(148, 163, 184, 0.16)"
        />
        <n-text depth="3" class="metric-caption">
          {{ item.value.filled }} of {{ documentCount }} documents
        </n-text>
      </div>
    </n-card>

    <n-card class="chart-card" :bordered="false">
      <template #header>
        <div>
          <div class="card-title">Accumulated pending days</div>
          <n-text depth="3" class="card-subtitle">Time spent in each workflow ownership</n-text>
        </div>
      </template>
      <div class="pending-surface">
        <Bar :data="pendingChartData" :options="pendingChartOptions" />
      </div>
    </n-card>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Bar, Line } from 'vue-chartjs'
import type { DashboardMetric, DashboardTimeline } from '@/models/compdocDashboard'
import { useUserStore } from '@/stores/user'
import { resolvePreferredTheme } from '@/services/theme'
import { createPendingChartData, createTimelineChartData } from '@/services/compdocChartData'
import { ensureCompdocChartsRegistered } from '@/services/compdocChartTheme'
import {
  createPendingChartOptions,
  createTimelineChartOptions
} from '@/services/compdocChartAxisOptions'

const props = defineProps<{
  documentCount: number
  timeline: DashboardTimeline
  performance: Record<'scheduled' | 'actual' | 'approved', DashboardMetric>
  pendingDays: Record<'authority' | 'ubm' | 'aw', number>
}>()

ensureCompdocChartsRegistered()
const userStore = useUserStore()
const theme = computed(() => resolvePreferredTheme(userStore.getPreferences))
const hasTimeline = computed(
  () => props.timeline.scheduled.length > 0 || props.timeline.actual.length > 1
)
const chartData = computed(() => createTimelineChartData(props.timeline, props.documentCount))
const chartOptions = computed(() =>
  createTimelineChartOptions(theme.value, props.timeline.today[0]?.x, props.documentCount)
)
const pendingChartData = computed(() => createPendingChartData(props.pendingDays))
const pendingChartOptions = computed(() => createPendingChartOptions(theme.value))
const metrics = computed(() => [
  { key: 'scheduled', label: 'Scheduled', value: props.performance.scheduled, color: '#64748b' },
  { key: 'actual', label: 'Issued', value: props.performance.actual, color: '#2563eb' },
  {
    key: 'approved',
    label: 'Authority approved',
    value: props.performance.approved,
    color: '#22c55e'
  }
])
</script>

<style scoped>
.timeline-stack {
  display: grid;
  gap: 16px;
  min-width: 0;
}

.chart-card,
.metric-card {
  background: linear-gradient(145deg, rgba(37, 99, 235, 0.04), transparent 44%);
}

.card-title {
  font-size: 16px;
  font-weight: 650;
}

.card-subtitle,
.metric-caption {
  font-size: 12px;
}

.timeline-surface {
  position: relative;
  height: 390px;
  min-width: 0;
}

.pending-surface {
  position: relative;
  height: 190px;
}

.metric + .metric {
  margin-top: 16px;
}

.metric-caption {
  display: block;
  margin-top: 3px;
}
</style>
