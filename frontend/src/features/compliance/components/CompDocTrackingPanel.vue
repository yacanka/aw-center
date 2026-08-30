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
watch(
  () => [props.show, props.document.id, props.project],
  ([show]) => {
    if (show) load()
  },
  { immediate: true }
)
async function load() {
  if (!props.document.id) return
  loading.value = true
  error.value = ''
  try {
    tracking.value = await fetchCompDocTracking(props.project, props.document.id)
    dirty.value = false
  } catch (cause) {
    error.value = formatApiError(cause)
  } finally {
    loading.value = false
  }
}
function applyPreferences(value: CompDocTrackingPreferenceValues) {
  if (!tracking.value) return
  Object.assign(tracking.value, value)
  dirty.value = true
}
async function save() {
  if (!tracking.value || !props.document.id) return
  await runAction(async () => {
    tracking.value = await saveCompDocTracking(props.project, props.document.id!, {
      responsible_mode: tracking.value!.responsible_mode,
      responsible_person_ids: tracking.value!.responsible_person_ids,
      notification_enabled: tracking.value!.notification_enabled,
      notification_events: tracking.value!.notification_events,
      version: tracking.value!.version
    })
    dirty.value = false
    window.$message.success('Tracking preferences saved.')
  })
}
async function refreshDocProof() {
  if (!tracking.value || !props.document.id || dirty.value) return
  await runAction(async () => {
    tracking.value = await refreshCompDocTracking(
      props.project,
      props.document.id!,
      tracking.value!.version
    )
    window.$message.success('DocProof evidence refreshed.')
  })
}
async function runAction(action: () => Promise<void>) {
  actionLoading.value = true
  error.value = ''
  try {
    await action()
  } catch (cause) {
    error.value = formatApiError(cause)
  } finally {
    actionLoading.value = false
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
