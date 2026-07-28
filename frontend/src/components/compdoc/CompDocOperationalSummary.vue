<script setup lang="ts">
import { useRouter } from 'vue-router'
import type { DashboardOperationalSummary } from '@/models/compdocDashboard'

const props = defineProps<{ project: string; operations: DashboardOperationalSummary }>()
const router = useRouter()
const metrics = [
  ['unassigned', 'Unassigned'],
  ['action_overdue', 'Action overdue'],
  ['action_due_soon', 'Action due soon'],
  ['pending_review', 'Pending review'],
  ['pending_approval', 'Pending approval'],
  ['archived', 'Archived']
] as const

function open(key: (typeof metrics)[number][0]) {
  void router.push({
    name: 'compdocs',
    params: { project: props.project },
    query: props.operations.filters[key]
  })
}
</script>

<template>
  <n-card title="Operational pulse" size="small" class="operations-card">
    <div class="operations-grid">
      <n-button
        v-for="[key, label] in metrics"
        :key="key"
        quaternary
        class="operation"
        @click="open(key)"
      >
        <span class="operation-value">{{ operations[key] }}</span>
        <span>{{ label }}</span>
      </n-button>
    </div>
  </n-card>
</template>

<style scoped>
.operations-card {
  margin-bottom: 12px;
}

.operations-grid {
  display: grid;
  grid-template-columns: repeat(6, minmax(110px, 1fr));
  gap: 8px;
}

.operation {
  height: auto;
  min-height: 64px;
}

.operation :deep(.n-button__content) {
  display: grid;
  gap: 2px;
}

.operation-value {
  font-size: 20px;
  font-weight: 700;
}

@media (max-width: 900px) {
  .operations-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}
</style>
