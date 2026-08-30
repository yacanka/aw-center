<template>
  <n-space vertical size="large">
    <n-card title="IBM Rational DOORS Agent">
      <n-alert :type="readinessType" :bordered="false">
        {{ readinessMessage }}
      </n-alert>
      <n-form label-placement="top" style="margin-top: 16px">
        <n-form-item label="Module path">
          <n-input v-model:value="modulePath" placeholder="/Project/System Requirements" />
        </n-form-item>
        <n-space>
          <n-button
            type="primary"
            :loading="queueing"
            :disabled="!canQueue"
            @click="queueModuleCheck"
          >
            Queue module check
          </n-button>
          <n-button :loading="statusLoading" @click="loadStatus">Refresh bridge status</n-button>
        </n-space>
      </n-form>
    </n-card>

    <n-alert v-if="lastJob" type="info" title="Windows automation queued">
      Job {{ lastJob.id }} will run when an authenticated Windows agent claims it.
      <template #action>
        <n-button text type="primary" @click="openJob">Open in Job Center</n-button>
      </template>
    </n-alert>
  </n-space>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { formatApiError } from '@/shared/api/apiError'
import {
  enqueueDoorsModuleCheck,
  fetchDoorsStatus,
  type DoorsStatus
} from '@/features/integrations/api/doorsAutomation'
import type { Job } from '@/features/jobs/api/jobs'

const router = useRouter()
const modulePath = ref('')
const bridge = ref<DoorsStatus | null>(null)
const lastJob = ref<Job | null>(null)
const statusLoading = ref(false)
const queueing = ref(false)
let pendingAttempt: { fingerprint: string; key: string } | null = null

const canQueue = computed(() => Boolean(bridge.value?.available && modulePath.value.trim()))
const readinessType = computed(() => (bridge.value?.available ? 'success' : 'warning'))
const readinessMessage = computed(() => {
  if (!bridge.value) return 'Windows automation availability has not been verified.'
  if (!bridge.value.configured) return 'The outbound Windows bridge is not configured.'
  if (!bridge.value.available) return 'No authenticated Windows automation agent is currently live.'
  return `${bridge.value.active_agents} Windows automation agent(s) available.`
})

onMounted(loadStatus)

async function loadStatus(): Promise<void> {
  statusLoading.value = true
  try {
    bridge.value = await fetchDoorsStatus()
  } catch (error) {
    bridge.value = null
    window.$message.error(formatApiError(error))
  } finally {
    statusLoading.value = false
  }
}

async function queueModuleCheck(): Promise<void> {
  const path = modulePath.value.trim()
  if (!bridge.value?.available || !path) return
  const fingerprint = JSON.stringify({ operation: 'check_module', module_path: path })
  if (pendingAttempt?.fingerprint !== fingerprint) {
    pendingAttempt = { fingerprint, key: crypto.randomUUID() }
  }

  queueing.value = true
  try {
    lastJob.value = await enqueueDoorsModuleCheck(path, pendingAttempt.key)
    pendingAttempt = null
    window.$message.success('DOORS module check queued.')
  } catch (error) {
    window.$message.error(formatApiError(error))
  } finally {
    queueing.value = false
  }
}

function openJob(): void {
  if (lastJob.value) void router.push({ path: '/jobs', query: { job: lastJob.value.id } })
}
</script>
