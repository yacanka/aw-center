<template>
  <n-space vertical size="large">
    <n-card title="Teamcenter Integration">
      <n-space vertical>
        <n-alert :type="status?.configured ? 'success' : 'warning'" :bordered="false">
          {{ statusMessage }}
        </n-alert>
        <n-descriptions v-if="status" :column="isNarrow ? 1 : 3" bordered>
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

    <n-card v-if="canAdminister" title="Property Update Job">
      <n-space vertical>
        <n-alert type="warning" :bordered="false">
          This external write is queued as an idempotent job. Review its terminal state in Job
          Center; the browser never performs a synchronous Teamcenter mutation.
        </n-alert>
        <n-form-item label="Validated updates JSON">
          <n-input
            v-model:value="propertyUpdatesJson"
            type="textarea"
            :autosize="{ minRows: 8, maxRows: 18 }"
          />
        </n-form-item>
        <n-space>
          <n-button
            type="warning"
            :loading="isQueueingUpdate"
            :disabled="!status?.configured"
            @click="queuePropertyUpdate"
          >
            Queue property update
          </n-button>
          <n-button v-if="lastUpdateJob" text type="primary" @click="openUpdateJob">
            Open job {{ lastUpdateJob.id }}
          </n-button>
        </n-space>
      </n-space>
    </n-card>
  </n-space>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { formatApiError } from '@/shared/api/apiError'
import {
  enqueueTeamcenterPropertyUpdate,
  fetchTeamcenterSavedQueries,
  fetchTeamcenterStatus,
  loadTeamcenterObjects,
  probeTeamcenter,
  type TeamcenterPropertyUpdate,
  type TeamcenterStatus
} from '@/features/integrations/api/teamcenter'
import { useSessionStore } from '@/features/session/stores/session'
import type { Job } from '@/features/jobs/api/jobs'
import { useMediaQuery } from '@/shared/composables/mediaQuery'

const router = useRouter()
const session = useSessionStore()
const isNarrow = useMediaQuery('(max-width: 700px)')
const status = ref<TeamcenterStatus | null>(null)
const savedQueries = ref<Record<string, unknown> | null>(null)
const objects = ref<Record<string, unknown> | null>(null)
const objectUids = ref('')
const isProbing = ref(false)
const isLoadingQueries = ref(false)
const isLoadingObjects = ref(false)
const isQueueingUpdate = ref(false)
const lastUpdateJob = ref<Job | null>(null)
const propertyUpdatesJson = ref(
  JSON.stringify(
    {
      updates: [
        {
          object: { uid: 'UID-1', type: 'WorkspaceObject' },
          properties: { object_name: ['Reviewed name'] }
        }
      ]
    },
    null,
    2
  )
)
let propertyUpdateAttempt: { fingerprint: string; key: string } | null = null

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
const canAdminister = computed(() =>
  Boolean(session.getUser.is_staff || session.getUser.is_superuser)
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

async function queuePropertyUpdate(): Promise<void> {
  const updates = parsePropertyUpdates(propertyUpdatesJson.value)
  if (!updates) return
  const fingerprint = JSON.stringify(updates)
  if (propertyUpdateAttempt?.fingerprint !== fingerprint) {
    propertyUpdateAttempt = { fingerprint, key: crypto.randomUUID() }
  }

  isQueueingUpdate.value = true
  try {
    lastUpdateJob.value = await enqueueTeamcenterPropertyUpdate(updates, propertyUpdateAttempt.key)
    propertyUpdateAttempt = null
    window.$message.success('Teamcenter property update queued.')
  } catch (error) {
    window.$message.error(formatApiError(error))
  } finally {
    isQueueingUpdate.value = false
  }
}

function parsePropertyUpdates(source: string): TeamcenterPropertyUpdate[] | null {
  try {
    const payload: unknown = JSON.parse(source)
    if (!isRecord(payload) || !Array.isArray(payload.updates) || !payload.updates.length) {
      throw new Error('Provide a non-empty updates array.')
    }
    if (!payload.updates.every(isPropertyUpdate)) {
      throw new Error('Each update needs an object UID and string-list properties.')
    }
    return payload.updates
  } catch (error) {
    window.$message.error(error instanceof Error ? error.message : 'Updates JSON is invalid.')
    return null
  }
}

function isPropertyUpdate(value: unknown): value is TeamcenterPropertyUpdate {
  if (!isRecord(value) || !isRecord(value.object) || !isRecord(value.properties)) return false
  return (
    typeof value.object.uid === 'string' &&
    Boolean(value.object.uid.trim()) &&
    Object.keys(value.properties).length > 0 &&
    Object.values(value.properties).every(
      (items) =>
        Array.isArray(items) && items.length > 0 && items.every((item) => typeof item === 'string')
    )
  )
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Object.prototype.toString.call(value) === '[object Object]'
}

function openUpdateJob(): void {
  if (lastUpdateJob.value) {
    void router.push({ name: 'jobs', query: { job: lastUpdateJob.value.id } })
  }
}

function formatJson(value: unknown) {
  return JSON.stringify(value, null, 2)
}
</script>
