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
  <n-alert
    v-else-if="dataQualityIssues"
    type="warning"
    title="Data quality needs attention"
    style="margin-bottom: 12px"
  >
    {{ qualityMessage }} Dashboard totals remain available; affected workflow values were isolated.
  </n-alert>

  <n-spin :show="loading">
    <n-empty v-if="!summary && !loading" description="No dashboard data is available." />
    <template v-else-if="summary">
      <n-flex justify="space-between" align="center" class="summary-meta">
        <n-text
          ><strong>{{ summary.document_count }}</strong> compliance documents</n-text
        >
        <n-text depth="3">Updated {{ formattedGeneratedAt }}</n-text>
      </n-flex>
      <div class="dashboard-grid">
        <div class="dashboard-column">
          <CompDocPanelDashboard
            :loading="loading"
            :panels="summary.panels"
            :selected-panel="selectedPanel?.panel"
            @select="togglePanel"
          />
          <CompDocStatusDashboard
            :counts="focusedCounts"
            :selected-panel="selectedPanel?.panel"
            @clear-panel="selectedPanel = null"
          />
        </div>
        <CompDocTimelineDashboard
          :document-count="summary.document_count"
          :timeline="summary.timeline"
          :performance="summary.performance"
          :pending-days="summary.pending_days"
        />
      </div>
    </template>
  </n-spin>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { DashboardPanel } from '@/models/compdocDashboard'
import { isoToTurkishDateTime } from '@/utils/time'
import { useCompdocDashboard } from '@/composables/compdoc/dashboard'
import CompDocPanelDashboard from './CompDocPanelDashboard.vue'
import CompDocStatusDashboard from './CompDocStatusDashboard.vue'
import CompDocTimelineDashboard from './CompDocTimelineDashboard.vue'

const { activeProject, dataQualityIssues, error, loading, loadProject, projectOptions, summary } =
  useCompdocDashboard()
const selectedPanel = ref<DashboardPanel | null>(null)

const focusedCounts = computed<Record<string, number>>(() => {
  const source = selectedPanel.value || summary.value?.status_counts || {}
  return Object.fromEntries(
    Object.entries(source).filter(
      ([key, value]) => !['panel', 'total'].includes(key) && typeof value === 'number'
    )
  ) as Record<string, number>
})
const formattedGeneratedAt = computed(() =>
  summary.value?.generated_at ? isoToTurkishDateTime(summary.value.generated_at) : ''
)
const qualityMessage = computed(() => {
  const quality = summary.value?.data_quality
  if (!quality) return ''
  return [
    quality.invalid_status_flow && `${quality.invalid_status_flow} invalid workflow`,
    quality.invalid_dates && `${quality.invalid_dates} invalid date`,
    quality.out_of_order_dates && `${quality.out_of_order_dates} out-of-order date`,
    quality.missing_panel && `${quality.missing_panel} missing panel`,
    quality.unknown_status && `${quality.unknown_status} unknown status`
  ]
    .filter(Boolean)
    .join(', ')
})

watch(activeProject, () => (selectedPanel.value = null))

function togglePanel(panel: DashboardPanel) {
  selectedPanel.value = selectedPanel.value?.panel === panel.panel ? null : panel
}
</script>

<style scoped>
.summary-meta {
  margin: 4px 0 12px;
}

.dashboard-grid {
  display: grid;
  grid-template-columns: minmax(520px, 1.08fr) minmax(420px, 0.92fr);
  gap: 16px;
  align-items: start;
}

.dashboard-column {
  display: grid;
  gap: 16px;
  min-width: 0;
}

@media (max-width: 1180px) {
  .dashboard-grid {
    grid-template-columns: 1fr;
  }
}
</style>
