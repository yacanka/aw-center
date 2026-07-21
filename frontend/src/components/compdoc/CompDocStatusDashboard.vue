<template>
  <n-card class="dashboard-card" :bordered="false">
    <template #header>
      <n-flex align="center" justify="space-between">
        <div>
          <div class="card-title">Document status</div>
          <n-text depth="3" class="card-subtitle">Current workflow distribution</n-text>
        </div>
        <n-tag v-if="selectedPanel" closable size="small" @close="$emit('clear-panel')">
          {{ selectedPanel }}
        </n-tag>
      </n-flex>
    </template>
    <div class="status-layout">
      <div class="chart-surface">
        <Doughnut
          v-if="total"
          :data="chartData"
          :options="chartOptions"
          :plugins="[centerTextPlugin]"
        />
        <n-empty v-else description="No status data" size="small" />
      </div>
      <div class="status-list">
        <div v-for="item in statusRows" :key="item.value" class="status-row">
          <span class="status-dot" :style="{ background: item.color }" />
          <span class="status-label">{{ item.label }}</span>
          <strong>{{ item.count }}</strong>
          <n-text depth="3">{{ item.percentage }}%</n-text>
          <span class="status-rail">
            <span
              class="status-fill"
              :style="{ width: `${item.percentage}%`, background: item.color }"
            />
          </span>
        </div>
      </div>
    </div>
  </n-card>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Doughnut } from 'vue-chartjs'
import { useUserStore } from '@/stores/user'
import { resolvePreferredTheme } from '@/services/theme'
import { createStatusChartData, createStatusChartRows } from '@/services/compdocChartData'
import {
  centerTextPlugin,
  createStatusChartOptions,
  ensureCompdocChartsRegistered
} from '@/services/compdocChartTheme'

const props = defineProps<{
  counts: Record<string, number>
  selectedPanel?: string
}>()
defineEmits<{ 'clear-panel': [] }>()

ensureCompdocChartsRegistered()
const userStore = useUserStore()
const theme = computed(() => resolvePreferredTheme(userStore.getPreferences))
const statusRows = computed(() => createStatusChartRows(props.counts))
const total = computed(() => statusRows.value.reduce((sum, row) => sum + row.count, 0))
const chartData = computed(() => createStatusChartData(statusRows.value))
const chartOptions = computed(() => createStatusChartOptions(theme.value))
</script>

<style scoped>
.dashboard-card {
  width: 100%;
  background: linear-gradient(145deg, rgba(59, 130, 246, 0.045), transparent 45%);
}

.card-title {
  font-size: 16px;
  font-weight: 650;
}

.card-subtitle {
  font-size: 12px;
}

.status-layout {
  display: grid;
  grid-template-columns: minmax(240px, 0.9fr) minmax(270px, 1.1fr);
  gap: 24px;
  align-items: center;
}

.chart-surface {
  position: relative;
  height: 310px;
  min-width: 0;
}

.status-list {
  display: grid;
  gap: 10px;
}

.status-row {
  display: grid;
  grid-template-columns: 10px minmax(140px, 1fr) 34px 42px;
  gap: 8px;
  align-items: center;
}

.status-dot {
  width: 9px;
  height: 9px;
  border-radius: 50%;
  box-shadow: 0 0 0 3px rgba(148, 163, 184, 0.12);
}

.status-label {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.status-rail {
  grid-column: 2 / 5;
  height: 3px;
  overflow: hidden;
  background: rgba(148, 163, 184, 0.16);
  border-radius: 999px;
}

.status-fill {
  display: block;
  height: 100%;
  min-width: 2px;
  border-radius: inherit;
  transition: width 300ms ease;
}

@media (max-width: 720px) {
  .status-layout {
    grid-template-columns: 1fr;
  }
}
</style>
