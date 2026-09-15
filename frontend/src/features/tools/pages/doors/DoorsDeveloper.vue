<template>
  <n-space vertical size="large">
    <n-card title="Developer / DOORS Automation Jobs">
      <n-alert :type="worker?.available ? 'success' : 'warning'" title="Windows worker execution">
        Browser requests only queue validated jobs. The Windows DOORS worker performs the operation
        without browser credentials, arbitrary DXL, or direct COM access from this server.
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
        <n-button :loading="statusLoading" @click="loadStatus">Refresh worker status</n-button>
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

    <n-alert v-if="lastError || errorMessage" type="error">
      {{ lastError || errorMessage }}
    </n-alert>
    <PageJobStatus
      :job="job"
      :cancelling="cancelling"
      :downloading="downloading"
      @cancel="cancel"
      @download="download"
      @open="openJobCenter"
    />
    <n-alert v-if="job?.error_code" type="error" :title="job.error_code">
      {{ job.message }}
    </n-alert>
    <n-card v-if="job?.status === 'succeeded'" title="DOORS operation result">
      <n-space vertical>
        <n-text v-if="resultLoading">Loading operation result…</n-text>
        <n-alert v-if="resultError" type="error">
          {{ resultError }}
          <n-button :loading="resultLoading" @click="loadResult(job)"
            >Retry loading result</n-button
          >
        </n-alert>
        <template v-if="result">
          <n-alert
            :type="result.operation_result.outcome === 'negative' ? 'warning' : 'success'"
            :title="resultTitle"
          >
            {{ result.operation_result.message }}
          </n-alert>
          <n-text>Result code: {{ result.operation_result.code }}</n-text>
          <n-text>Module: {{ result.operation_result.input.module_path }}</n-text>
          <n-text v-if="result.absolute_number">Object: {{ result.absolute_number }}</n-text>
          <n-button v-if="result.absolute_number" @click="useResultObject">
            Use this object for the next operation
          </n-button>
          <n-text>Input</n-text>
          <n-code :code="inputText" language="json" word-wrap />
          <n-text>Output</n-text>
          <n-code :code="outputText" language="json" word-wrap />
        </template>
      </n-space>
    </n-card>
  </n-space>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { formatApiError } from '@/shared/api/apiError'
import PageJobStatus from '@/features/jobs/components/PageJobStatus.vue'
import { usePageJob } from '@/features/jobs/composables/usePageJob'
import {
  enqueueDoorsModuleCheck,
  enqueueDoorsObjectCreate,
  enqueueDoorsObjectUpdate,
  fetchDoorsStatus,
  fetchDoorsDeveloperResult,
  type DoorsDeveloperResult,
  type DoorsStatus,
  type DoorsPosition,
  type DoorsScalarAttributes
} from '@/features/integrations/api/doorsAutomation'
import type { Job } from '@/features/jobs/api/jobs'

type Operation = 'check' | 'update' | 'create'

const {
  job,
  active,
  cancelling,
  downloading,
  errorMessage,
  cancel,
  download,
  openJobCenter,
  setJob
} = usePageJob('doors_developer_job')
const modulePath = ref('')
const absoluteNumber = ref(1)
const position = ref<DoorsPosition>('after')
const relativeAbsoluteNumber = ref(1)
const attributesJson = ref(
  '{\n  "Object Heading": "Developer test",\n  "Object Text": "DOORS job test"\n}'
)
const worker = ref<DoorsStatus | null>(null)
const statusLoading = ref(false)
const busy = ref<Operation | null>(null)
const lastError = ref('')
const result = ref<DoorsDeveloperResult | null>(null)
const resultLoading = ref(false)
const resultError = ref('')
let disposed = false
const attempts = new Map<Operation, { fingerprint: string; key: string }>()

const positionOptions = ['first', 'after', 'before', 'below', 'below_last'].map((value) => ({
  label: value,
  value
}))
const canQueue = computed(() =>
  Boolean(
    worker.value?.available &&
    modulePath.value.trim() &&
    !busy.value &&
    !active.value &&
    !resultLoading.value
  )
)
const inputText = computed(() => JSON.stringify(result.value?.operation_result.input, null, 2))
const outputText = computed(() => {
  if (!result.value) return ''
  const { operation_result: metadata, ...output } = result.value
  return JSON.stringify({ ...output, code: metadata.code, outcome: metadata.outcome }, null, 2)
})
const resultTitle = computed(() => {
  if (result.value?.operation_result.operation === 'check_module') {
    return result.value.accessible
      ? 'Module found and readable'
      : 'Module not found or no read access'
  }
  return result.value?.operation_result.operation === 'create_object'
    ? 'Object created'
    : 'Attributes updated'
})

onMounted(loadStatus)
onBeforeUnmount(() => {
  disposed = true
})
watch(
  () => [job.value?.id, job.value?.status],
  () => {
    result.value = null
    resultError.value = ''
    if (job.value?.status === 'succeeded') void loadResult(job.value)
  }
)

async function loadResult(completedJob: Job): Promise<void> {
  resultLoading.value = true
  resultError.value = ''
  try {
    const loaded = await fetchDoorsDeveloperResult(completedJob)
    if (!disposed && job.value?.id === completedJob.id) result.value = loaded
  } catch (error) {
    if (!disposed && job.value?.id === completedJob.id) resultError.value = formatApiError(error)
  } finally {
    if (!disposed && job.value?.id === completedJob.id) resultLoading.value = false
  }
}

function useResultObject(): void {
  if (!result.value?.absolute_number) return
  modulePath.value = result.value.operation_result.input.module_path
  absoluteNumber.value = result.value.absolute_number
  relativeAbsoluteNumber.value = result.value.absolute_number
}

async function loadStatus(): Promise<void> {
  statusLoading.value = true
  try {
    worker.value = await fetchDoorsStatus()
  } catch (error) {
    worker.value = null
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
  if (!canQueue.value) return
  const fingerprint = JSON.stringify(input)
  const currentAttempt = attempts.get(operation)
  if (!currentAttempt || currentAttempt.fingerprint !== fingerprint) {
    attempts.set(operation, { fingerprint, key: crypto.randomUUID() })
  }

  busy.value = operation
  lastError.value = ''
  try {
    const queuedJob = await action(attempts.get(operation)!.key)
    setJob(queuedJob)
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
</script>
