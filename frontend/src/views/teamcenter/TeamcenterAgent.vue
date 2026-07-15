<template>
  <n-space vertical size="large">
    <n-card title="Teamcenter Integration">
      <n-space vertical>
        <n-alert :type="status?.configured ? 'success' : 'warning'" :bordered="false">
          {{ statusMessage }}
        </n-alert>
        <n-descriptions v-if="status" :column="3" bordered>
          <n-descriptions-item label="Authentication">{{ status.auth_mode }}</n-descriptions-item>
          <n-descriptions-item label="Service root">{{ status.service_root }}</n-descriptions-item>
          <n-descriptions-item label="TLS verification">
            {{ status.tls_verification_enabled ? 'Enabled' : 'Disabled' }}
          </n-descriptions-item>
        </n-descriptions>
        <n-button
          type="primary"
          :loading="isProbing"
          :disabled="!status?.configured"
          @click="verifyConnection"
        >
          Verify connection
        </n-button>
      </n-space>
    </n-card>

    <n-card title="Read Operations">
      <n-tabs type="line">
        <n-tab-pane name="queries" tab="Saved Queries">
          <n-space vertical>
            <n-button :loading="isLoadingQueries" @click="loadSavedQueries">
              Load saved queries
            </n-button>
            <n-code
              v-if="savedQueries"
              :code="formatJson(savedQueries)"
              language="json"
              word-wrap
            />
          </n-space>
        </n-tab-pane>
        <n-tab-pane name="objects" tab="Load Objects">
          <n-form label-placement="top">
            <n-form-item label="Object UIDs (comma or newline separated)">
              <n-input
                v-model:value="objectUids"
                type="textarea"
                placeholder="UID-1, UID-2"
                :autosize="{ minRows: 3, maxRows: 8 }"
              />
            </n-form-item>
            <n-button
              type="primary"
              :loading="isLoadingObjects"
              :disabled="parsedUids.length === 0"
              @click="loadObjects"
            >
              Load objects
            </n-button>
          </n-form>
          <n-code v-if="objects" :code="formatJson(objects)" language="json" word-wrap />
        </n-tab-pane>
      </n-tabs>
    </n-card>
  </n-space>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { formatApiError } from '@/services/apiError'
import {
  fetchTeamcenterSavedQueries,
  fetchTeamcenterStatus,
  loadTeamcenterObjects,
  probeTeamcenter,
  type TeamcenterStatus
} from '@/services/engineeringIntegrations'

const status = ref<TeamcenterStatus | null>(null)
const savedQueries = ref<Record<string, unknown> | null>(null)
const objects = ref<Record<string, unknown> | null>(null)
const objectUids = ref('')
const isProbing = ref(false)
const isLoadingQueries = ref(false)
const isLoadingObjects = ref(false)

const statusMessage = computed(() =>
  status.value?.configured
    ? 'Teamcenter server-side configuration is ready.'
    : 'Teamcenter environment variables are incomplete.'
)
const parsedUids = computed(() =>
  objectUids.value
    .split(/[\n,]/)
    .map((value) => value.trim())
    .filter(Boolean)
    .slice(0, 250)
)

onMounted(loadStatus)

async function loadStatus() {
  try {
    status.value = await fetchTeamcenterStatus()
  } catch (error) {
    window.$message.error(formatApiError(error))
  }
}

async function verifyConnection() {
  isProbing.value = true
  try {
    await probeTeamcenter()
    window.$message.success('Teamcenter connection verified.')
  } catch (error) {
    window.$message.error(formatApiError(error))
  } finally {
    isProbing.value = false
  }
}

async function loadSavedQueries() {
  isLoadingQueries.value = true
  try {
    savedQueries.value = await fetchTeamcenterSavedQueries()
  } catch (error) {
    window.$message.error(formatApiError(error))
  } finally {
    isLoadingQueries.value = false
  }
}

async function loadObjects() {
  isLoadingObjects.value = true
  try {
    objects.value = await loadTeamcenterObjects(parsedUids.value)
  } catch (error) {
    window.$message.error(formatApiError(error))
  } finally {
    isLoadingObjects.value = false
  }
}

function formatJson(value: unknown) {
  return JSON.stringify(value, null, 2)
}
</script>
