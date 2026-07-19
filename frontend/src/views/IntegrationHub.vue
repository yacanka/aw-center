<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { fetchIntegrationCatalog, type IntegrationItem } from '@/services/integrationHub'
import { formatApiError } from '@/services/apiError'

const integrations = ref<IntegrationItem[]>([])
const loading = ref(false)
const errorMessage = ref('')
const router = useRouter()

const readyCount = computed(
  () => integrations.value.filter((item) => item.status === 'ready').length
)
const availableCount = computed(
  () => integrations.value.filter((item) => item.health?.status === 'available').length
)
const hasLiveResults = computed(() => integrations.value.some((item) => item.health))

async function loadIntegrations(probe = false, refresh = false) {
  loading.value = true
  errorMessage.value = ''
  try {
    integrations.value = await fetchIntegrationCatalog(probe, refresh)
  } catch (error) {
    errorMessage.value = formatApiError(error)
  } finally {
    loading.value = false
  }
}

function configurationType(item: IntegrationItem) {
  return item.status === 'ready' ? 'success' : 'warning'
}

function healthType(item: IntegrationItem) {
  if (item.health?.status === 'available') return 'success'
  if (item.health?.status === 'degraded') return 'warning'
  if (item.health?.status === 'unavailable') return 'error'
  return 'default'
}

function healthLabel(item: IntegrationItem) {
  return item.health?.status.replaceAll('_', ' ') || 'not checked'
}

function checkedAt(item: IntegrationItem) {
  if (!item.health?.checked_at) return ''
  return new Intl.DateTimeFormat(undefined, { dateStyle: 'short', timeStyle: 'medium' }).format(
    new Date(item.health.checked_at)
  )
}

function runLiveChecks(refresh = false) {
  return loadIntegrations(true, refresh)
}

function openIntegration(item: IntegrationItem) {
  if (item.route) router.push(item.route)
}

onMounted(() => loadIntegrations())
</script>

<template>
  <n-space vertical size="large">
    <n-page-header title="Integration Hub" subtitle="One center for engineering bridges">
      <template #extra>
        <n-space align="center">
          <n-tag type="success">{{ readyCount }} / {{ integrations.length }} configured</n-tag>
          <n-tag v-if="hasLiveResults" type="info">
            {{ availableCount }} / {{ integrations.length }} live
          </n-tag>
          <n-button size="small" :loading="loading" @click="runLiveChecks(true)">
            Run live checks
          </n-button>
        </n-space>
      </template>
    </n-page-header>

    <n-alert v-if="errorMessage" type="error" title="Integration catalog unavailable">
      {{ errorMessage }}
      <template #action>
        <n-button size="small" @click="loadIntegrations()">Retry</n-button>
      </template>
    </n-alert>

    <n-spin :show="loading">
      <n-grid cols="1 s:2 l:3" responsive="screen" :x-gap="16" :y-gap="16">
        <n-grid-item v-for="item in integrations" :key="item.id">
          <n-card :title="item.name" hoverable class="integration-card">
            <n-space vertical>
              <n-space size="small" class="status-row">
                <n-tag :type="configurationType(item)" size="small">
                  {{ item.status === 'ready' ? 'Configured' : 'Needs configuration' }}
                </n-tag>
                <n-tag v-if="item.health" :type="healthType(item)" size="small">
                  {{ healthLabel(item) }}
                </n-tag>
              </n-space>
              <n-text depth="3">{{ item.description }}</n-text>
              <n-alert v-if="item.health" :type="healthType(item)" :show-icon="false">
                {{ item.health.detail }}
              </n-alert>
              <n-text v-if="item.health" depth="3" class="health-meta">
                {{ checkedAt(item) }} · {{ item.health.latency_ms ?? 0 }} ms ·
                {{ item.health.source }}
              </n-text>
              <n-space size="small">
                <n-tag v-for="capability in item.capabilities" :key="capability" size="small">
                  {{ capability }}
                </n-tag>
              </n-space>
              <n-button
                v-if="item.route"
                type="primary"
                secondary
                :disabled="item.status !== 'ready'"
                @click="openIntegration(item)"
              >
                Open
              </n-button>
            </n-space>
          </n-card>
        </n-grid-item>
      </n-grid>
    </n-spin>
  </n-space>
</template>

<style scoped>
.integration-card {
  height: 100%;
}

.health-meta {
  text-transform: capitalize;
}

.status-row {
  min-height: 24px;
}
</style>
