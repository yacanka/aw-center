<template>
  <n-card class="action-center" size="small">
    <template #header>
      <n-space align="center">
        <span>Needs attention</span>
        <n-tag v-if="summary.critical" size="small" type="error">
          {{ summary.critical }} critical
        </n-tag>
        <n-tag v-if="summary.warning" size="small" type="warning">
          {{ summary.warning }} warning
        </n-tag>
      </n-space>
    </template>
    <template #header-extra>
      <n-button quaternary size="small" :loading="loading" @click="loadItems">Refresh</n-button>
    </template>

    <n-alert v-if="errorMessage" type="error" :bordered="false">
      {{ errorMessage }}
    </n-alert>
    <n-skeleton v-else-if="loading && !items.length" text :repeat="3" />
    <n-alert v-else-if="!items.length" type="success" :bordered="false">
      No recent workflow needs intervention.
    </n-alert>
    <n-list v-else hoverable clickable>
      <n-list-item v-for="item in items" :key="item.id" @click="openItem(item)">
        <n-thing :title="item.title" :description="item.detail">
          <template #header-extra>
            <n-tag size="small" :type="item.severity === 'critical' ? 'error' : 'warning'">
              {{ kindLabel(item.kind) }}
            </n-tag>
          </template>
          <n-space vertical size="small">
            <n-text>{{ item.guidance }}</n-text>
            <n-text depth="3">
              {{ item.due_at ? `Due ${formatDate(item.due_at)}` : formatDate(item.occurred_at) }}
            </n-text>
          </n-space>
          <template #action>
            <n-space>
              <n-button size="small" type="primary" @click.stop="openItem(item)">
                {{ item.action_label }}
              </n-button>
              <n-button
                size="small"
                secondary
                :loading="activeDecision === item.id"
                @click.stop="decide(item, 'snooze')"
              >
                Snooze 24h
              </n-button>
              <n-button size="small" quaternary @click.stop="confirmDismiss(item)">
                Dismiss
              </n-button>
            </n-space>
          </template>
        </n-thing>
      </n-list-item>
    </n-list>
  </n-card>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { formatApiError } from '@/services/apiError'
import {
  fetchActionCenter,
  updateAttentionDecision,
  type AttentionDecisionAction,
  type AttentionItem,
  type AttentionKind,
  type AttentionSummary
} from '@/services/actionCenter'

const router = useRouter()
const items = ref<AttentionItem[]>([])
const summary = ref<AttentionSummary>({ total: 0, critical: 0, warning: 0 })
const loading = ref(false)
const errorMessage = ref('')
const activeDecision = ref('')

onMounted(loadItems)

async function loadItems(): Promise<void> {
  loading.value = true
  try {
    const response = await fetchActionCenter()
    items.value = response.items
    summary.value = response.summary
    errorMessage.value = ''
  } catch (error) {
    errorMessage.value = formatApiError(error)
  } finally {
    loading.value = false
  }
}

async function openItem(item: AttentionItem): Promise<void> {
  await router.push(item.action_path)
}

async function decide(item: AttentionItem, action: AttentionDecisionAction): Promise<void> {
  activeDecision.value = item.id
  try {
    await updateAttentionDecision(item.id, action)
    removeItem(item)
    window.$message.success(action === 'snooze' ? 'Snoozed for 24 hours.' : 'Item dismissed.')
    await loadItems()
  } catch (error) {
    window.$message.error(formatApiError(error))
  } finally {
    activeDecision.value = ''
  }
}

function confirmDismiss(item: AttentionItem): void {
  window.$dialog.warning({
    title: 'Dismiss attention item',
    content: 'Hide this item from your Action Center? The underlying record will not change.',
    positiveText: 'Dismiss',
    negativeText: 'Keep',
    onPositiveClick: () => decide(item, 'dismiss')
  })
}

function removeItem(item: AttentionItem): void {
  items.value = items.value.filter((candidate) => candidate.id !== item.id)
  summary.value.total = Math.max(summary.value.total - 1, 0)
  summary.value[item.severity] = Math.max(summary.value[item.severity] - 1, 0)
}

function kindLabel(kind: AttentionKind): string {
  return { job: 'Job', import: 'Import', invitation: 'Invitation', jira_draft: 'JIRA draft' }[kind]
}

function formatDate(value: string): string {
  return new Intl.DateTimeFormat(undefined, { dateStyle: 'short', timeStyle: 'short' }).format(
    new Date(value)
  )
}
</script>

<style scoped>
.action-center {
  margin-bottom: 16px;
}
</style>
