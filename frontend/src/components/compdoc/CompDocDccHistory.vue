<template>
  <n-card v-if="allowed" title="DCC Traceability" size="small">
    <n-spin :show="loading">
      <n-alert v-if="errorMessage" type="error" :bordered="false">
        {{ errorMessage }}
        <template #action><n-button text @click="load">Retry</n-button></template>
      </n-alert>
      <n-empty v-else-if="!loading && !traces.length" description="Not used in a confirmed DCC" />
      <n-timeline v-else>
        <n-timeline-item
          v-for="trace in traces"
          :key="trace.id"
          :type="timelineType(trace)"
          :title="trace.issue_key"
          :time="formatDate(trace.confirmed_at)"
        >
          <n-space vertical size="small">
            <n-space>
              <n-tag size="small" :type="statusType(trace.job_status)">
                {{ readableTraceStatus(trace.job_status) }}
              </n-tag>
              <n-tag size="small" :type="sourceVersionTagType(trace)">
                {{ sourceVersionLabel(trace) }}
              </n-tag>
              <n-tag v-if="trace.output_available" size="small" type="success">
                Output ready
              </n-tag>
            </n-space>
            <n-text depth="3">
              History #{{ trace.source_history_id ?? 'Unavailable' }} · Source
              {{ formatDate(trace.source_history_at) }} · Attempt {{ trace.job_attempt ?? '—' }}
            </n-text>
            <n-alert
              v-if="!trace.is_current_version"
              :type="sourceChangeAlertType(trace)"
              :bordered="false"
            >
              {{ sourceChangeMessage(trace) }}
              <n-space v-if="trace.source_change.changed_fields.length" style="margin-top: 6px">
                <n-tag
                  v-for="field in trace.source_change.changed_fields"
                  :key="field.code"
                  size="small"
                  type="warning"
                >
                  {{ field.label }}
                </n-tag>
              </n-space>
            </n-alert>
            <n-code :code="trace.source_fingerprint" language="text" word-wrap />
            <n-button
              v-if="trace.can_open_job && trace.job_id"
              size="small"
              secondary
              type="primary"
              @click="openJob(trace.job_id)"
            >
              Open in Job Center
            </n-button>
            <CompDocDccRefresh :trace="trace" />
          </n-space>
        </n-timeline-item>
      </n-timeline>
      <n-pagination
        v-if="count > PAGE_SIZE"
        :page="page"
        :page-size="PAGE_SIZE"
        :item-count="count"
        @update:page="changePage"
      />
    </n-spin>
  </n-card>
</template>

<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { formatApiError } from '@/services/apiError'
import CompDocDccRefresh from '@/components/compdoc/CompDocDccRefresh.vue'
import { fetchCompdocDccTraces, type CompdocDccTrace } from '@/services/compdocTraceability'
import {
  readableTraceStatus,
  sourceChangeAlertType,
  sourceChangeMessage,
  sourceVersionLabel,
  sourceVersionTagType,
  traceStatusType as statusType,
  traceTimelineType as timelineType
} from '@/services/compdocTracePresentation'

const PAGE_SIZE = 5
const props = defineProps<{ project: string; compdocId: string; allowed: boolean }>()
const router = useRouter()
const traces = ref<CompdocDccTrace[]>([])
const count = ref(0)
const page = ref(1)
const loading = ref(false)
const errorMessage = ref('')
let requestController: AbortController | null = null

watch(() => [props.project, props.compdocId, props.allowed], resetAndLoad, { immediate: true })
onBeforeUnmount(cancelRequest)

async function load(): Promise<void> {
  if (!props.allowed || !props.compdocId) return
  cancelRequest()
  const controller = new AbortController()
  requestController = controller
  loading.value = true
  errorMessage.value = ''
  try {
    await loadTracePage(controller)
  } catch (error) {
    if (!controller.signal.aborted) errorMessage.value = formatApiError(error)
  } finally {
    if (requestController === controller) loading.value = false
  }
}

async function loadTracePage(controller: AbortController): Promise<void> {
  const result = await fetchCompdocDccTraces(
    props.project,
    props.compdocId,
    page.value,
    PAGE_SIZE,
    controller.signal
  )
  if (requestController !== controller) return
  traces.value = result.results
  count.value = result.count
}

function resetAndLoad(): void {
  page.value = 1
  traces.value = []
  count.value = 0
  if (props.allowed) void load()
}

function changePage(nextPage: number): void {
  page.value = nextPage
  void load()
}

function cancelRequest(): void {
  requestController?.abort()
  requestController = null
}

function openJob(jobId: string): void {
  void router.push({ name: 'jobs', query: { job: jobId } })
}

function formatDate(value: string | null): string {
  if (!value) return 'Unavailable'
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: 'medium',
    timeStyle: 'medium'
  }).format(new Date(value))
}
</script>
