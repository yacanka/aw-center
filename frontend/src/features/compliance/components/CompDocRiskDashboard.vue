<template>
  <n-card class="risk-card" :bordered="false">
    <template #header>
      <n-flex justify="space-between" align="center">
        <div>
          <div class="card-title">Explainable risk priorities</div>
          <n-text depth="3" class="card-subtitle">
            Top {{ risk.policy.priority_limit }}, ranked by target dates, release age and missing
            metadata
          </n-text>
        </div>
        <n-select
          v-model:value="selectedLevel"
          :options="levelOptions"
          size="small"
          style="width: 150px"
        />
      </n-flex>
    </template>

    <div class="risk-summary">
      <div v-for="item in summaryItems" :key="item.level" class="summary-item">
        <span class="summary-dot" :style="{ background: item.color }" />
        <span>{{ item.label }}</span>
        <strong>{{ item.count }}</strong>
      </div>
      <div class="summary-item summary-item--average">
        <span>Average score</span>
        <strong>{{ risk.average_score }}</strong>
      </div>
    </div>

    <n-empty v-if="!visiblePriorities.length" :description="emptyDescription" size="small" />
    <n-scrollbar v-else style="max-height: 470px; height: auto">
      <n-collapse accordion>
        <n-collapse-item
          v-for="priority in visiblePriorities"
          :key="priority.document_id"
          :name="priority.document_id"
        >
          <template #header>
            <div class="priority-header">
              <n-tag :color="priorityColor(priority.level)" :bordered="false" round size="small">
                {{ priority.score }} / {{ risk.policy.max_score }}
              </n-tag>
              <div class="priority-name">
                <strong>{{ priority.name }}</strong>
                <n-text depth="3">
                  {{ priority.panel }} · ATA {{ priority.ata || '—' }} ·
                  {{ statusLabel(priority.status) }}
                </n-text>
              </div>
              <n-tag
                size="small"
                :bordered="false"
                title="Workflow stage age is informational and adds no risk points."
                >Stage: {{ priority.stage_age_days }} days</n-tag
              >
            </div>
          </template>
          <div class="signal-list">
            <div v-for="signal in priority.signals" :key="signal.code" class="signal-item">
              <n-flex justify="space-between" align="center">
                <n-tag :type="levelType(signal.severity)" size="small">
                  {{ signal.label }}
                </n-tag>
                <strong>+{{ signal.points }}</strong>
              </n-flex>
              <n-text depth="3">{{ signal.detail }}</n-text>
            </div>
            <n-button text type="primary" @click="reviewDocument(priority.document_id)">
              Review document
            </n-button>
          </div>
        </n-collapse-item>
      </n-collapse>
    </n-scrollbar>

    <n-text depth="3" class="policy-note">
      Showing {{ risk.priorities.length }} of {{ risk.at_risk_count }} · policy v{{
        risk.policy.version
      }}
      · very high ≥ {{ risk.policy.very_high_score }} · high {{ risk.policy.high_score }}–{{
        risk.policy.very_high_score - 1
      }}
      · medium {{ risk.policy.medium_score }}–{{ risk.policy.high_score - 1 }} · low 0–{{
        risk.policy.medium_score - 1
      }}. Low includes zero-score documents; only positive scores enter the priority list. Scores
      are capped at {{ risk.policy.max_score }}.
    </n-text>
  </n-card>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useThemeVars } from 'naive-ui'
import { accessibleTagColors } from '@/features/compliance/api/compdocStatusColors'
import type {
  DashboardRiskLevel,
  DashboardRiskSeverity,
  DashboardRiskSummary
} from '@/features/compliance/models/compdocDashboard'
import { STATUS_PRESENTATION } from '@/features/compliance/api/compdocChartData'

const props = defineProps<{ project: string; risk: DashboardRiskSummary }>()
const router = useRouter()
const themeVars = useThemeVars()
const selectedLevel = ref('all')
const levelOptions = [
  { label: 'All priorities', value: 'all' },
  { label: 'Very high risk', value: 'very_high' },
  { label: 'High risk', value: 'high' },
  { label: 'Medium risk', value: 'medium' },
  { label: 'Low risk', value: 'low' }
]
const levelPresentation = [
  { level: 'very_high', label: 'Very high', color: '#881337' },
  { level: 'high', label: 'High', color: '#ef4444' },
  { level: 'medium', label: 'Medium', color: '#f59e0b' },
  { level: 'low', label: 'Low', color: '#3b82f6' }
] as const
const summaryItems = computed(() =>
  levelPresentation.map((item) => ({ ...item, count: props.risk.counts[item.level] || 0 }))
)
const visiblePriorities = computed(() =>
  selectedLevel.value === 'all'
    ? props.risk.priorities
    : props.risk.priorities.filter((item) => item.level === selectedLevel.value)
)
const emptyDescription = computed(() =>
  props.risk.at_risk_count
    ? `No ${selectedLevel.value} priorities in the top ${props.risk.policy.priority_limit}.`
    : 'No active risk signals.'
)

function priorityColor(level: DashboardRiskLevel) {
  const color = levelPresentation.find((item) => item.level === level)!.color
  return accessibleTagColors(color, themeVars.value.cardColor)
}

function levelType(level: DashboardRiskSeverity) {
  if (level === 'high') return 'error'
  if (level === 'medium') return 'warning'
  return 'info'
}

function statusLabel(value: string) {
  return STATUS_PRESENTATION.find((status) => status.value === value)?.label || value
}

function reviewDocument(document: string) {
  void router.push({ name: 'compdocs', params: { project: props.project }, query: { document } })
}
</script>

<style scoped src="./CompDocRiskDashboard.css"></style>
