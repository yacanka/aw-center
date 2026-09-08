<script setup lang="ts">
import { ref, watch } from 'vue'
import { formatApiError } from '@/shared/api/apiError'
import type { ICompDoc } from '@/features/compliance/models/compdocs'
import {
  type CompDocTracking,
  type CompDocTrackingPreferenceValues,
  docproofTagType,
  fetchCompDocTracking,
  formatTrackingTimestamp,
  refreshCompDocTracking,
  saveCompDocTracking
} from '@/features/compliance/api/compdocTracking'
import CompDocTrackingPreferences from './CompDocTrackingPreferences.vue'
import './CompDocTrackingPanel.css'

const props = defineProps<{
  show: boolean
  document: ICompDoc
  project: string
  canEdit: boolean
}>()
const tracking = ref<CompDocTracking | null>(null)
const loading = ref(false)
const actionLoading = ref(false)
const error = ref('')
const dirty = ref(false)
let loadSequence = 0
watch(
  () => [props.show, props.document.id, props.project],
  ([show]) => {
    loadSequence += 1
    loading.value = false
    actionLoading.value = false
    tracking.value = null
    dirty.value = false
    if (show) void load()
  },
  { immediate: true }
)
async function load() {
  if (!props.document.id) return
  const sequence = ++loadSequence
  const documentId = props.document.id
  const project = props.project
  loading.value = true
  error.value = ''
  try {
    const loaded = await fetchCompDocTracking(project, documentId)
    if (sequence !== loadSequence) return
    tracking.value = loaded
    dirty.value = false
  } catch (cause) {
    if (sequence === loadSequence) error.value = formatApiError(cause)
  } finally {
    if (sequence === loadSequence) loading.value = false
  }
}
function applyPreferences(value: CompDocTrackingPreferenceValues) {
  if (!tracking.value) return
  Object.assign(tracking.value, value)
  dirty.value = true
}
async function save() {
  if (!tracking.value || !props.document.id) return
  const sequence = loadSequence
  const documentId = props.document.id
  const project = props.project
  await runAction(async () => {
    const updated = await saveCompDocTracking(project, documentId, {
      responsible_mode: tracking.value!.responsible_mode,
      responsible_person_ids: tracking.value!.responsible_person_ids,
      notification_enabled: tracking.value!.notification_enabled,
      notification_events: tracking.value!.notification_events,
      version: tracking.value!.version
    })
    if (sequence !== loadSequence) return
    tracking.value = updated
    dirty.value = false
    window.$message.success('Tracking preferences saved.')
  })
}
async function refreshDocProof() {
  if (!tracking.value || !props.document.id || dirty.value) return
  const sequence = loadSequence
  const documentId = props.document.id
  const project = props.project
  await runAction(async () => {
    const updated = await refreshCompDocTracking(project, documentId, tracking.value!.version)
    if (sequence !== loadSequence) return
    tracking.value = updated
    window.$message.success('DocProof evidence refreshed.')
  })
}
async function runAction(action: () => Promise<void>) {
  const sequence = loadSequence
  actionLoading.value = true
  error.value = ''
  try {
    await action()
  } catch (cause) {
    if (sequence === loadSequence) error.value = formatApiError(cause)
  } finally {
    if (sequence === loadSequence) actionLoading.value = false
  }
}
</script>
<template>
  <section class="workspace-section">
    <n-spin :show="loading || actionLoading">
      <n-space v-if="tracking" vertical class="tracking-stack">
        <n-alert v-if="error" type="error" :bordered="false">{{ error }}</n-alert>
        <n-card title="DocProof revision" size="small">
          <n-flex justify="space-between" align="center" class="tracking-docproof-row">
            <n-flex align="center">
              <n-tag :type="docproofTagType(tracking.docproof_status)">
                {{ tracking.docproof_status }}
              </n-tag>
              <n-text> DocProof issue {{ tracking.docproof_issue || '—' }} </n-text>
            </n-flex>
            <n-button v-if="canEdit" size="small" :disabled="dirty" @click="refreshDocProof">
              Refresh
            </n-button>
          </n-flex>
          <n-text depth="3">
            Last checked {{ formatTrackingTimestamp(tracking.docproof_checked_at) }}
          </n-text>
        </n-card>
        <CompDocTrackingPreferences
          :tracking="tracking"
          :disabled="!canEdit"
          :project="project"
          @change="applyPreferences"
          @policy-saved="load"
        />
        <n-alert v-if="dirty" type="info" :bordered="false">
          Save these preferences before checking or sending an alert.
        </n-alert>
        <n-button v-if="canEdit" type="primary" :disabled="!dirty" @click="save">
          Save tracking
        </n-button>
      </n-space>
      <n-alert v-else-if="error" type="error" :bordered="false">
        {{ error }}
        <template #action><n-button size="small" @click="load">Retry</n-button></template>
      </n-alert>
    </n-spin>
  </section>
</template>
