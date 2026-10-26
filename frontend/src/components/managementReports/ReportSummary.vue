<script setup lang="ts">
import { computed, h } from 'vue'
import { NProgress, type DataTableColumns } from 'naive-ui'
import type { ProjectReportMetrics, ReportEnvelope } from '@/models/managementReports'
import { formatReportDelta } from '@/services/managementReportHelpers'
import { isoToTurkishDateTime } from '@/utils/time'

const props = defineProps<{ envelope: ReportEnvelope }>()
const cards = computed(() => [
  ['Active documents', props.envelope.report.totals.document_count],
  ['Authority approved', `${props.envelope.report.totals.approval_percentage}%`],
  ['Issued', props.envelope.report.totals.issued_count],
  ['High risk', props.envelope.report.totals.high_risk_count],
  ['Overdue actions', props.envelope.report.totals.action_overdue_count],
  ['Unassigned', props.envelope.report.totals.unassigned_count]
])
const changes = computed(() => {
  const deltas = props.envelope.comparison.deltas
  return [
    ['Approved documents', formatReportDelta(deltas?.approved_count ?? null)],
    ['Approval rate', formatReportDelta(deltas?.approval_percentage ?? null, true)],
    ['Overdue actions', formatReportDelta(deltas?.action_overdue_count ?? null)],
    ['High-risk documents', formatReportDelta(deltas?.high_risk_count ?? null)]
  ]
})
const columns: DataTableColumns<ProjectReportMetrics> = [
  { title: 'Project', key: 'display_name', width: 150, fixed: 'left' },
  { title: 'Documents', key: 'document_count', width: 110 },
  { title: 'Issued', key: 'issued_count', width: 85 },
  { title: 'Approved', key: 'approved_count', width: 95 },
  {
    title: 'Approval rate',
    key: 'approval_percentage',
    width: 170,
    render: (row) =>
      h(NProgress, {
        type: 'line',
        percentage: row.approval_percentage,
        indicatorPlacement: 'inside'
      })
  },
  { title: 'Scheduled', key: 'scheduled_count', width: 105 },
  { title: 'Issued − scheduled', key: 'schedule_variance', width: 155 },
  { title: 'High risk', key: 'high_risk_count', width: 95 },
  { title: 'Overdue', key: 'action_overdue_count', width: 90 },
  { title: 'Due in 7 days', key: 'action_due_soon_count', width: 125 },
  { title: 'Unassigned', key: 'unassigned_count', width: 110 },
  { title: 'Review tasks', key: 'pending_review_count', width: 115 },
  { title: 'Approval tasks', key: 'pending_approval_count', width: 125 },
  { title: 'Quality issues', key: 'data_quality_issue_count', width: 120 }
]
</script>

<template>
  <n-alert v-if="!envelope.report.totals.document_count" type="info" title="Empty portfolio">
    No active compliance documents exist in this scope. Approval is 0%.
  </n-alert>
  <div class="metric-grid">
    <n-card v-for="[label, value] in cards" :key="label" size="small">
      <n-text depth="3">{{ label }}</n-text>
      <div class="metric-value">{{ value }}</div>
    </n-card>
  </div>
  <n-card title="Net change since previous report" size="small">
    <template v-if="envelope.comparison.available && envelope.comparison.baseline">
      <n-text depth="3">
        {{ isoToTurkishDateTime(envelope.comparison.baseline.captured_at) }} →
        {{ isoToTurkishDateTime(envelope.report.captured_at) }} ·
        {{ envelope.comparison.elapsed_days }} days
      </n-text>
      <div class="change-grid">
        <div v-for="[label, value] in changes" :key="label">
          <div class="change-value">{{ value }}</div>
          <n-text>{{ label }}</n-text>
        </div>
      </div>
    </template>
    <n-empty
      v-else
      size="small"
      description="No compatible snapshot from the previous calendar week."
    />
    <n-p depth="3" class="definition">
      Differences are net changes in the same portfolio, not counts of events during the period.
      Approval differences use percentage points. An explicit older baseline may be selected below.
    </n-p>
  </n-card>
  <n-card title="Project overview" size="small">
    <n-data-table
      :columns="columns"
      :data="envelope.report.projects"
      :row-key="(row: ProjectReportMetrics) => row.slug"
      :scroll-x="1755"
      size="small"
    />
  </n-card>
  <n-card title="Document priorities" size="small">
    <n-empty
      v-if="!envelope.report.priorities.length"
      size="small"
      description="No active risk priorities in this scope."
    />
    <n-list v-else>
      <n-list-item
        v-for="priority in envelope.report.priorities"
        :key="`${priority.project_slug}:${priority.document_id}`"
      >
        <n-thing :title="`${priority.project_name} · ${priority.name}`">
          <n-space align="center">
            <n-tag :type="priority.level === 'high' ? 'error' : 'warning'" size="small"
              >{{ priority.level }} · {{ priority.score }}</n-tag
            >
            <n-text>{{ priority.stage_age_days }} days in stage</n-text>
            <n-text>Owner: {{ priority.owner || 'Unassigned' }}</n-text>
            <n-text>Next action: {{ priority.next_action_due_date || 'Not set' }}</n-text>
          </n-space>
          <n-p>{{ priority.reason }}</n-p>
        </n-thing>
      </n-list-item>
    </n-list>
    <n-text depth="3"
      >Document priorities identify evidence to review; they are not management decisions.</n-text
    >
  </n-card>
  <n-card v-if="envelope.report.management_note" title="Management note" size="small">
    <div class="management-note">{{ envelope.report.management_note }}</div>
  </n-card>
  <n-text depth="3" class="definition">
    Approval = authority-approved / active documents. Issued and approved are separate stages.
    Schedule variance = issued − scheduled; it is not a forecast. Review/approval counts are tasks.
    Data-quality counts represent issues, not unique documents. Capture time is not external-source
    freshness.
  </n-text>
</template>

<style scoped>
.metric-grid {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 12px;
}
.metric-value {
  font-size: 28px;
  font-weight: 650;
  margin-top: 8px;
  font-variant-numeric: tabular-nums;
}
.change-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 16px;
  margin-top: 16px;
}
.change-value {
  font-size: 22px;
  font-weight: 650;
  font-variant-numeric: tabular-nums;
}
.definition {
  font-size: 12px;
  line-height: 1.6;
}
.management-note {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
@media (max-width: 1100px) {
  .metric-grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}
@media (max-width: 650px) {
  .metric-grid,
  .change-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
