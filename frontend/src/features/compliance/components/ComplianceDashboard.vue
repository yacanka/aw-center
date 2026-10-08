<template>
  <n-tabs :value="activeProject" @update:value="loadProject">
    <n-tab-pane
      v-for="project in projectOptions"
      :key="project.value"
      :name="project.value"
      :tab="project.label"
      :disabled="project.disabled"
    />
  </n-tabs>

  <n-alert v-if="error" type="error" title="Dashboard could not be loaded" class="dashboard-alert">
    {{ error }}
    <n-button v-if="activeProject" size="small" @click="loadProject(activeProject)">Retry</n-button>
  </n-alert>

  <n-spin :show="loading">
    <n-empty v-if="!summary && !loading" description="No dashboard data is available." />
    <template v-else-if="summary && focusedAnalytics">
      <n-flex justify="space-between" align="center" class="summary-meta">
        <n-flex align="center">
          <n-tag v-if="selectedPanel" closable type="info" @close="clearPanel">
            {{ selectedPanel.panel
            }}<template v-if="selectedPanel.ata"> · {{ selectedPanel.ata }}</template>
          </n-tag>
          <n-text v-else>All panels</n-text>
          <n-text depth="3" class="scope-caption"
            >Charts and risk priorities share this scope.</n-text
          >
        </n-flex>
        <n-flex align="center">
          <n-text depth="3" class="scope-caption">Updated {{ formattedGeneratedAt }}</n-text>
          <n-button size="small" :loading="loading" @click="loadProject(activeProject)"
            >Refresh</n-button
          >
        </n-flex>
      </n-flex>
      <n-grid cols="2 m:4" responsive="screen" :x-gap="12" :y-gap="12" class="metrics">
        <n-gi>
          <n-statistic label="Active documents" :value="focusedAnalytics.total" />
        </n-gi>
        <n-gi>
          <n-statistic label="Overdue actions" :value="focusedAnalytics.overdue" />
        </n-gi>
        <n-gi>
          <n-statistic
            label="Documents with risk signals"
            :value="focusedAnalytics.risk.at_risk_count"
          />
        </n-gi>
        <n-gi>
          <n-statistic label="Archived in project" :value="summary.archived" />
        </n-gi>
      </n-grid>
      <n-alert
        v-if="focusedAnalytics.data_quality.issue_count"
        type="warning"
        title="Data quality needs attention"
        class="dashboard-alert"
      >
        {{ qualityMessage }}
      </n-alert>
      <CompDocPanelDashboard
        v-model:mode="breakdownMode"
        :statuses="summary.statuses"
        class="panel-breakdown"
        :loading="loading"
        :panels="displayedPanels"
        :selected-panel="selectedPanel?.id"
        @select="togglePanel"
      />
      <div class="dashboard-grid">
        <div class="dashboard-column">
          <CompDocStatusDashboard
            :statuses="summary.statuses"
            :counts="focusedAnalytics.chart_status_counts"
            :groups="publicationGroups"
            subtitle="Delivery status · percentages of all documents"
          />
          <CompDocStatusDashboard
            title="Document CAT"
            subtitle="Category distribution"
            empty-description="No CAT data"
            :counts="focusedAnalytics.cat_counts"
            :rows="catRows"
          >
            <template #distribution-extra>
              <section class="moc-distribution">
                <h3 class="distribution-heading">Not issued by MoC</h3>
                <div v-for="item in mocRows" :key="item.value" class="moc-row">
                  <span>{{ item.label }}</span>
                  <strong>{{ item.count }}</strong>
                  <n-text depth="3">{{ item.percentage }}%</n-text>
                </div>
                <n-text v-if="!mocRows.length" depth="3">No unissued documents</n-text>
              </section>
            </template>
          </CompDocStatusDashboard>
        </div>
        <CompDocTimelineDashboard
          :document-count="focusedAnalytics.total"
          :timeline="focusedAnalytics.timeline"
          :performance="focusedAnalytics.performance"
          :pending-days="focusedAnalytics.pending_days"
        />
      </div>
      <CompDocRiskDashboard :project="activeProject" :risk="focusedAnalytics.risk" />
    </template>
  </n-spin>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useThemeVars } from 'naive-ui'
import {
  createCatChartRows,
  createStatusChartRows
} from '@/features/compliance/api/compdocChartData'
import { useCompdocDashboard } from '@/features/compliance/composables/dashboard'
import { isoToTurkishDateTime } from '@/shared/utils/time'
import CompDocPanelDashboard from './CompDocPanelDashboard.vue'
import CompDocRiskDashboard from './CompDocRiskDashboard.vue'
import CompDocStatusDashboard from './CompDocStatusDashboard.vue'
import CompDocTimelineDashboard from './CompDocTimelineDashboard.vue'

const {
  activeProject,
  breakdownMode,
  displayedPanels,
  error,
  loading,
  loadProject,
  projectOptions,
  summary,
  focusedAnalytics,
  selectedPanel,
  togglePanel,
  clearPanel
} = useCompdocDashboard()
const themeVars = useThemeVars()
const catRows = computed(() => {
  const colors = themeVars.value
  return createCatChartRows(
    focusedAnalytics.value?.cat_counts ?? {},
    [
      colors.primaryColor,
      colors.infoColor,
      colors.warningColor,
      colors.successColor,
      colors.errorColor
    ],
    colors.textColor3
  )
})
const publicationGroups = computed(() => {
  const analytics = focusedAnalytics.value
  if (!analytics) return []
  return (['issued', 'not_issued'] as const).map((key) => {
    const group = analytics.publication[key]
    const options =
      key === 'issued'
        ? summary.value?.statuses
        : [
            { value: 'delayed', label: 'Delayed' },
            { value: 'expected', label: 'Expected' },
            { value: 'missing_target', label: 'Target date missing' }
          ]
    return {
      label: key === 'issued' ? 'Issued' : 'Not issued',
      total: group.total,
      rows: createStatusChartRows(group.status_counts, options, themeVars.value.textColor3).map(
        (row) => ({
          ...row,
          percentage: analytics.total ? Math.round((row.count / analytics.total) * 100) : 0
        })
      )
    }
  })
})
const mocRows = computed(() =>
  createCatChartRows(
    focusedAnalytics.value?.unissued_moc_counts ?? {},
    [],
    themeVars.value.textColor3
  ).map((row) => ({ ...row, label: row.value ? `MoC ${row.value}` : row.label }))
)
const formattedGeneratedAt = computed(() =>
  summary.value ? isoToTurkishDateTime(summary.value.generated_at) : ''
)
const qualityMessage = computed(() => {
  const quality = focusedAnalytics.value?.data_quality
  if (!quality) return ''
  return [
    quality.missing_panel && `${quality.missing_panel} missing panel`,
    quality.unknown_status && `${quality.unknown_status} unknown status`,
    quality.blank_cover_page && `${quality.blank_cover_page} blank cover page`,
    quality.out_of_order_dates && `${quality.out_of_order_dates} out-of-order workflow dates`
  ]
    .filter(Boolean)
    .join(' · ')
})
</script>

<style scoped>
.moc-distribution {
  border-top: 1px solid v-bind('themeVars.dividerColor');
  padding-top: 12px;
}

.distribution-heading {
  margin: 0 0 10px;
  font-size: 15px;
  color: v-bind('themeVars.textColor1');
}

.moc-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 34px 42px;
  gap: 8px;
  align-items: center;
  margin-top: 8px;
}

.summary-meta {
  margin: 8px 0 16px;
}

.scope-caption {
  font-size: 12px;
}

.dashboard-alert,
.panel-breakdown {
  margin-bottom: 16px;
}

.dashboard-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.08fr) minmax(0, 0.92fr);
  gap: 16px;
  align-items: start;
  margin-bottom: 16px;
}

.dashboard-column {
  display: grid;
  gap: 16px;
  min-width: 0;
}

.metrics {
  margin: 4px 0 16px;
}

.metrics :deep(.n-statistic) {
  padding: 16px;
  border-radius: 10px;
  background: rgba(100, 116, 139, 0.08);
  font-variant-numeric: tabular-nums;
}

@media (max-width: 1380px) {
  .dashboard-grid {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
