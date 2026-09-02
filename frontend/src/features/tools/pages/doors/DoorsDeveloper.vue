<template>
  <n-space vertical size="large">
    <n-card title="Developer / DOORS Automation Jobs">
      <n-alert :type="runner?.available ? 'success' : 'warning'" title="Host-local execution">
        Browser requests only queue validated jobs. The native Windows DOORS runner performs the
        operation without browser credentials, arbitrary DXL, or direct COM access from this server.
      </n-alert>
      <n-form label-placement="top" style="margin-top: 16px">
        <n-grid cols="1 700:2" responsive="screen" :x-gap="16">
          <n-form-item-gi label="Module path">
            <n-input v-model:value="modulePath" placeholder="/Project/Folder/Module" />
          </n-form-item-gi>
          <n-form-item-gi label="Absolute number">
            <n-input-number v-model:value="absoluteNumber" :min="1" style="width: 100%" />
          </n-form-item-gi>
          <n-form-item-gi label="Create position">
            <n-select v-model:value="position" :options="positionOptions" />
          </n-form-item-gi>
          <n-form-item-gi label="Relative absolute number">
            <n-input-number
              v-model:value="relativeAbsoluteNumber"
              :disabled="position === 'first'"
              :min="1"
              style="width: 100%"
            />
          </n-form-item-gi>
          <n-form-item-gi label="Scalar attributes JSON" :span="2">
            <n-input v-model:value="attributesJson" type="textarea" :autosize="{ minRows: 5 }" />
          </n-form-item-gi>
        </n-grid>
      </n-form>
      <n-space>
        <n-button :loading="statusLoading" @click="loadStatus">Refresh runner status</n-button>
        <n-button :disabled="!canQueue" :loading="busy === 'check'" @click="queueModuleCheck">
          Queue module check
        </n-button>
        <n-button
          type="warning"
          :disabled="!canQueue"
          :loading="busy === 'update'"
          @click="queueObjectUpdate"
        >
          Queue object update
        </n-button>
        <n-button
          type="error"
          :disabled="!canQueue"
          :loading="busy === 'create'"
          @click="queueObjectCreate"
        >
          Queue object create
        </n-button>
      </n-space>
    </n-card>

    <n-card title="Last queued job">
      <n-code :code="responseText" language="json" word-wrap />
      <template v-if="lastJob" #action>
        <n-button type="primary" @click="openJob">Open in Job Center</n-button>
      </template>
    </n-card>
  </n-space>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { formatApiError } from '@/shared/api/apiError'
import {
  enqueueDoorsModuleCheck,
  enqueueDoorsObjectCreate,
  enqueueDoorsObjectUpdate,
  fetchDoorsStatus,
  type DoorsStatus,
  type DoorsPosition,
  type DoorsScalarAttributes
} from '@/features/integrations/api/doorsAutomation'
import type { Job } from '@/features/jobs/api/jobs'

type Operation = 'check' | 'update' | 'create'

const router = useRouter()
const modulePath = ref('')
const absoluteNumber = ref(1)
const position = ref<DoorsPosition>('after')
const relativeAbsoluteNumber = ref(1)
const attributesJson = ref(
  '{\n  "Object Heading": "Developer test",\n  "Object Text": "DOORS job test"\n}'
)
const runner = ref<DoorsStatus | null>(null)
const statusLoading = ref(false)
const busy = ref<Operation | null>(null)
const lastJob = ref<Job | null>(null)
const lastError = ref('No request has been sent yet.')
const attempts = new Map<Operation, { fingerprint: string; key: string }>()

const positionOptions = ['first', 'after', 'before', 'below', 'below_last'].map((value) => ({
  label: value,
  value
}))
const canQueue = computed(() =>
  Boolean(runner.value?.available && modulePath.value.trim() && !busy.value)
)
const responseText = computed(() =>
  JSON.stringify(lastJob.value || { error: lastError.value }, null, 2)
)

onMounted(loadStatus)

async function loadStatus(): Promise<void> {
  statusLoading.value = true
  try {
    runner.value = await fetchDoorsStatus()
  } catch (error) {
    runner.value = null
    lastError.value = formatApiError(error)
  } finally {
    statusLoading.value = false
  }
}

async function queueModuleCheck(): Promise<void> {
  const input = { module_path: modulePath.value.trim() }
  await queue('check', input, (key) => enqueueDoorsModuleCheck(input.module_path, key))
}

async function queueObjectUpdate(): Promise<void> {
  const attributes = readScalarAttributes()
  if (!attributes) return
  const input = {
    module_path: modulePath.value.trim(),
    absolute_number: absoluteNumber.value,
    attributes
  }
  await queue('update', input, (key) => enqueueDoorsObjectUpdate(input, key))
}

async function queueObjectCreate(): Promise<void> {
  const attributes = readScalarAttributes()
  if (!attributes) return
  const input = {
    module_path: modulePath.value.trim(),
    position: position.value,
    ...(position.value === 'first'
      ? {}
      : { relative_absolute_number: relativeAbsoluteNumber.value }),
    attributes
  }
  await queue('create', input, (key) => enqueueDoorsObjectCreate(input, key))
}

async function queue(
  operation: Operation,
  input: object,
  action: (idempotencyKey: string) => Promise<Job>
): Promise<void> {
  if (!runner.value?.available || !modulePath.value.trim() || busy.value) return
  const fingerprint = JSON.stringify(input)
  const currentAttempt = attempts.get(operation)
  if (!currentAttempt || currentAttempt.fingerprint !== fingerprint) {
    attempts.set(operation, { fingerprint, key: crypto.randomUUID() })
  }

  busy.value = operation
  lastJob.value = null
  try {
    lastJob.value = await action(attempts.get(operation)!.key)
    attempts.delete(operation)
    lastError.value = ''
    window.$message.success('DOORS automation job queued.')
  } catch (error) {
    lastError.value = formatApiError(error)
    window.$message.error(lastError.value)
  } finally {
    busy.value = null
  }
}

function readScalarAttributes(): DoorsScalarAttributes | null {
  try {
    const parsed: unknown = JSON.parse(attributesJson.value)
    if (
      !isRecord(parsed) ||
      Object.keys(parsed).length === 0 ||
      Object.keys(parsed).length > 50 ||
      Object.values(parsed).some((value) => !isScalar(value))
    ) {
      throw new Error('Use a JSON object containing 1-50 scalar attributes.')
    }
    return parsed as DoorsScalarAttributes
  } catch (error) {
    window.$message.error(error instanceof Error ? error.message : 'Attributes JSON is invalid.')
    return null
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Object.prototype.toString.call(value) === '[object Object]'
}

function isScalar(value: unknown): boolean {
  return value === null || ['string', 'number', 'boolean'].includes(typeof value)
}

function openJob(): void {
  if (lastJob.value) void router.push({ path: '/jobs', query: { job: lastJob.value.id } })
}
</script>
