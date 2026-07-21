<template>
  <n-card class="risk-card" :bordered="false">
    <template #header>
      <n-flex justify="space-between" align="center">
        <div>
          <div class="card-title">Explainable risk priorities</div>
          <n-text depth="3" class="card-subtitle">
            Top {{ risk.policy.priority_limit }}, ranked by SLA, aging, workflow loops and
            references
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
    <n-scrollbar v-else style="max-height: 470px">
      <n-collapse accordion>
        <n-collapse-item
          v-for="priority in visiblePriorities"
          :key="priority.document_id"
          :name="priority.document_id"
        >
          <template #header>
            <div class="priority-header">
              <n-tag :type="levelType(priority.level)" round size="small">
                {{ priority.score }} / {{ risk.policy.max_score }}
              </n-tag>
              <div class="priority-name">
                <strong>{{ priority.name }}</strong>
                <n-text depth="3">
                  {{ priority.panel }} · ATA {{ priority.ata || '—' }} ·
                  {{ statusLabel(priority.status) }}
                </n-text>
              </div>
              <n-tag size="small" :bordered="false">{{ priority.stage_age_days }} days</n-tag>
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
            <n-button text type="primary" @click="reviewDocument(priority.name)">
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
      · high ≥ {{ risk.policy.high_score }} · medium ≥ {{ risk.policy.medium_score }} · long wait
      &gt; {{ risk.policy.long_wait_days }} days · authority aging &gt;
      {{ risk.policy.authority_aging_days }} days
    </n-text>
  </n-card>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import type { DashboardRiskLevel, DashboardRiskSummary } from '@/models/compdocDashboard'
import { STATUS_PRESENTATION } from '@/services/compdocChartData'

const props = defineProps<{ project: string; risk: DashboardRiskSummary }>()
const router = useRouter()
const selectedLevel = ref('all')
const levelOptions = [
  { label: 'All priorities', value: 'all' },
  { label: 'High risk', value: 'high' },
  { label: 'Medium risk', value: 'medium' },
  { label: 'Low risk', value: 'low' }
]
const levelPresentation = [
  { level: 'high', label: 'High', color: '#ef4444' },
  { level: 'medium', label: 'Medium', color: '#f59e0b' },
  { level: 'low', label: 'Low', color: '#3b82f6' },
  { level: 'none', label: 'No signals', color: '#22c55e' }
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

function levelType(level: DashboardRiskLevel) {
  if (level === 'high') return 'error'
  if (level === 'medium') return 'warning'
  if (level === 'low') return 'info'
  return 'success'
}

function statusLabel(value: string) {
  return STATUS_PRESENTATION.find((status) => status.value === value)?.label || value
}

function reviewDocument(name: string) {
  void router.push({ name: 'compdocs', params: { project: props.project }, query: { name } })
}
</script>

<style scoped src="./CompDocRiskDashboard.css"></style>
