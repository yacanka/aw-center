<script setup lang="ts">
import { ref, watch } from 'vue'
import { formatApiError } from '@/services/apiError'
import type { ICompDoc } from '@/models/compdocs'
import {
  checkCompDocRevision,
  type CompDocNotificationEvent,
  type CompDocTracking,
  type CompDocTrackingUpdate,
  docproofTagType,
  fetchCompDocTracking,
  formatTrackingTimestamp,
  saveCompDocTracking,
  sendCompDocNotification
} from '@/services/compdocTracking'
import CompDocNotificationActions from './CompDocNotificationActions.vue'
import CompDocNotificationHistory from './CompDocNotificationHistory.vue'
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
const eventToSend = ref<CompDocNotificationEvent>('overdue')
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
function applyPreferences(value: CompDocTrackingUpdate) {
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
      notification_events: tracking.value!.notification_events
    })
    dirty.value = false
    window.$message.success('Tracking preferences saved.')
  })
}
async function checkRevision() {
  if (!props.document.id) return
  await runAction(async () => {
    tracking.value = await checkCompDocRevision(props.project, props.document.id!)
    window.$message.success('DocProof status refreshed.')
  })
}
async function refreshPolicyProjection() {
  if (!tracking.value || !props.document.id) return
  try {
    const latest = await fetchCompDocTracking(props.project, props.document.id)
    tracking.value.event_states = latest.event_states
  } catch (cause) {
    error.value = formatApiError(cause)
  }
}
async function sendNow() {
  if (!props.document.id) return
  await runAction(async () => {
    const result = await sendCompDocNotification(
      props.project,
      props.document.id!,
      eventToSend.value
    )
    tracking.value = result.tracking
    const message = {
      sent: 'Notification sent.',
      failed: 'Mail transport or recipients are unavailable.',
      not_applicable: 'This alert is not currently applicable.',
      already_processed: 'This event was already delivered.'
    }[result.status]
    window.$message[result.status === 'sent' ? 'success' : 'warning'](message)
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
            <n-space align="center">
              <n-tag :type="docproofTagType(tracking.docproof.status)">
                {{ tracking.docproof.status }}
              </n-tag>
              <n-text>
                Recorded {{ tracking.document.tech_doc_issue || '—' }} · DocProof
                {{ tracking.docproof.issue || '—' }}
              </n-text>
            </n-space>
            <n-button v-if="canEdit" size="small" :disabled="dirty" @click="checkRevision">
              Check now
            </n-button>
          </n-flex>
          <n-text depth="3">
            Last checked {{ formatTrackingTimestamp(tracking.docproof.checked_at) }}
          </n-text>
        </n-card>
        <CompDocTrackingPreferences
          :tracking="tracking"
          :disabled="!canEdit"
          :project="project"
          @change="applyPreferences"
          @policy-saved="refreshPolicyProjection"
        />
        <n-alert v-if="dirty" type="info" :bordered="false">
          Save these preferences before checking or sending an alert.
        </n-alert>
        <n-button v-if="canEdit" type="primary" :disabled="!dirty" @click="save">
          Save tracking
        </n-button>
        <CompDocNotificationActions
          v-if="canEdit"
          v-model="eventToSend"
          :event-states="tracking.event_states"
          :project="project"
          :document-id="document.id || ''"
          :configured="tracking.configured"
          :disabled="dirty || actionLoading"
          @send="sendNow"
          @error="error = formatApiError($event)"
        />
        <CompDocNotificationHistory :items="tracking.recent_notifications" />
      </n-space>
      <n-alert v-else-if="error" type="error" :bordered="false">
        {{ error }}
        <template #action><n-button size="small" @click="load">Retry</n-button></template>
      </n-alert>
    </n-spin>
  </section>
</template>
