<template>
  <n-card title="Integration exceptions" size="small" class="home-card">
    <template #header-extra>
      <n-space>
        <n-button quaternary size="small" :loading="loading" @click="loadExceptions">
          Refresh
        </n-button>
        <n-button quaternary size="small" @click="openHub">View hub</n-button>
      </n-space>
    </template>
    <n-alert v-if="errorMessage" type="error" :bordered="false">{{ errorMessage }}</n-alert>
    <n-skeleton v-else-if="loading && !exceptions.length" text :repeat="3" />
    <n-alert v-else-if="checksPending" type="info" :bordered="false">
      Integration health checks are still refreshing.
    </n-alert>
    <n-alert v-else-if="!exceptions.length" type="success" :bordered="false">
      Configured integrations are healthy.
    </n-alert>
    <n-list v-else>
      <n-list-item v-for="item in exceptions.slice(0, 4)" :key="item.id">
        <n-thing :title="item.name" :description="exceptionDetail(item)">
          <template #header-extra>
            <n-tag size="small" :type="exceptionType(item)">{{ exceptionLabel(item) }}</n-tag>
          </template>
        </n-thing>
      </n-list-item>
    </n-list>
    <n-text v-if="exceptions.length > 4" depth="3">
      {{ exceptions.length - 4 }} more exception(s) available in Integration Hub.
    </n-text>
  </n-card>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { formatApiError } from '@/services/apiError'
import { integrationExceptions } from '@/services/homeDashboard'
import { fetchIntegrationCatalog, type IntegrationItem } from '@/services/integrationHub'

const router = useRouter()
const exceptions = ref<IntegrationItem[]>([])
const integrations = ref<IntegrationItem[]>([])
const loading = ref(false)
const errorMessage = ref('')
const checksPending = computed(() =>
  integrations.value.some((item) => item.health?.status === 'checking')
)

onMounted(loadExceptions)

async function loadExceptions(): Promise<void> {
  loading.value = true
  try {
    integrations.value = await fetchIntegrationCatalog(true)
    exceptions.value = integrationExceptions(integrations.value)
    errorMessage.value = ''
  } catch (error) {
    errorMessage.value = formatApiError(error)
  } finally {
    loading.value = false
  }
}

function exceptionLabel(item: IntegrationItem): string {
  if (item.status === 'attention') return 'needs configuration'
  return item.health?.status.replaceAll('_', ' ') || 'needs configuration'
}

function exceptionDetail(item: IntegrationItem): string {
  if (item.status === 'attention') return item.description
  return item.health?.detail || item.description
}

function exceptionType(item: IntegrationItem): 'warning' | 'error' {
  return item.health?.status === 'unavailable' ? 'error' : 'warning'
}

function openHub(): void {
  void router.push('/integrations')
}
</script>

<style scoped>
.home-card {
  height: 100%;
}
</style>
