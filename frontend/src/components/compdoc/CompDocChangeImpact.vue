<template>
  <n-card title="DCC change impact" size="small">
    <n-skeleton v-if="loading" text :repeat="2" />
    <n-alert v-else-if="errorMessage" type="error" :bordered="false">
      {{ errorMessage }}
      <template #action><n-button text @click="load">Retry</n-button></template>
    </n-alert>
    <n-alert v-else-if="traceCount === 0" type="success" :bordered="false">
      No confirmed DCC currently references this document.
    </n-alert>
    <n-alert v-else type="warning" :bordered="false">
      {{ traceCount }} confirmed DCC trace{{ traceCount === 1 ? '' : 's' }} reference this document.
      Saving creates a new source version; existing outputs stay immutable and will be flagged for
      review.
      <template #action>
        <n-checkbox v-model:checked="acknowledged" @update:checked="publishReadiness">
          I reviewed this impact
        </n-checkbox>
      </template>
    </n-alert>
    <n-space v-if="issueKeys.length" style="margin-top: 8px">
      <n-tag v-for="issueKey in issueKeys" :key="issueKey" size="small">
        {{ issueKey }}
      </n-tag>
      <n-text v-if="traceCount > issueKeys.length" depth="3">
        +{{ traceCount - issueKeys.length }} more
      </n-text>
    </n-space>
  </n-card>
</template>

<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'
import { formatApiError } from '@/services/apiError'
import { fetchCompdocDccTraces } from '@/services/compdocTraceability'

const props = defineProps<{
  project: string
  compdocId: string
  sourceHistoryId?: number
  active: boolean
}>()
const emit = defineEmits<{ ready: [value: boolean] }>()
const loading = ref(false)
const errorMessage = ref('')
const traceCount = ref(0)
const issueKeys = ref<string[]>([])
const acknowledged = ref(false)
let requestController: AbortController | null = null

watch(() => [props.active, props.project, props.compdocId, props.sourceHistoryId], refresh, {
  immediate: true
})
onBeforeUnmount(cancelRequest)

async function load(): Promise<void> {
  cancelRequest()
  const controller = new AbortController()
  requestController = controller
  loading.value = true
  errorMessage.value = ''
  emit('ready', false)
  try {
    await loadImpact(controller)
  } catch (error) {
    if (!controller.signal.aborted) errorMessage.value = formatApiError(error)
  } finally {
    if (requestController === controller) loading.value = false
  }
}

async function loadImpact(controller: AbortController): Promise<void> {
  const page = await fetchCompdocDccTraces(props.project, props.compdocId, 1, 5, controller.signal)
  if (requestController !== controller) return
  traceCount.value = page.count
  issueKeys.value = [...new Set(page.results.map((trace) => trace.issue_key))]
  emit('ready', page.count === 0)
}

function refresh(): void {
  acknowledged.value = false
  traceCount.value = 0
  issueKeys.value = []
  emit('ready', false)
  if (!props.active) return cancelRequest()
  if (!props.sourceHistoryId) {
    errorMessage.value = 'Reload the document before editing.'
    return
  }
  void load()
}

function publishReadiness(): void {
  emit('ready', traceCount.value === 0 || acknowledged.value)
}

function cancelRequest(): void {
  requestController?.abort()
  requestController = null
}
</script>
