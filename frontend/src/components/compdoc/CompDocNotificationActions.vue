<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import {
  downloadCompDocNotificationDraft,
  type CompDocNotificationEvent,
  type CompDocNotificationEventState
} from '@/services/compdocTracking'
import { saveBlobAsFile } from '@/services/download'

const props = defineProps<{
  eventStates: CompDocNotificationEventState[]
  project: string
  documentId: string
  configured: boolean
  disabled: boolean
}>()
const eventType = defineModel<CompDocNotificationEvent>({ required: true })
const emit = defineEmits<{ send: []; error: [cause: unknown] }>()
const loading = ref(false)
const selectedState = computed(() =>
  props.eventStates.find((state) => state.value === eventType.value)
)
const eventOptions = computed(() => props.eventStates.map(({ value, label }) => ({ value, label })))
const ready = computed(
  () =>
    props.configured &&
    Boolean(selectedState.value?.recipient_count) &&
    Boolean(selectedState.value?.applicable)
)
const stateAlertType = computed(() =>
  ready.value ? 'success' : selectedState.value?.applicable ? 'warning' : 'info'
)
const stateHeader = computed(() => {
  if (ready.value) return 'Ready for action'
  return selectedState.value?.applicable ? 'Event condition detected' : 'Not currently applicable'
})
const actionDisabled = computed(() => props.disabled || loading.value || !ready.value)

watch(
  () => props.eventStates,
  (states) => {
    if (states.some((state) => state.value === eventType.value && state.applicable)) return
    const applicable = states.find((state) => state.applicable)
    if (applicable) eventType.value = applicable.value
  },
  { immediate: true }
)

function confirmSend() {
  if (!ready.value || !selectedState.value) return
  window.$dialog.warning({
    title: 'Send compliance notification?',
    content: `${selectedState.value.label} will be sent to ${recipientSummary()}. AW Center cannot recall a delivered email.`,
    positiveText: 'Send notification',
    negativeText: 'Cancel',
    onPositiveClick: () => emit('send')
  })
}

function recipientSummary() {
  const state = selectedState.value!
  const escalation = state.escalation_recipient_count
    ? ` and ${state.escalation_recipient_count} escalation CC`
    : ''
  return `${state.primary_recipient_count} primary contact(s)${escalation}`
}

async function downloadDraft() {
  if (!ready.value) return
  loading.value = true
  try {
    const draft = await downloadCompDocNotificationDraft(
      props.project,
      props.documentId,
      eventType.value
    )
    saveBlobAsFile(draft.blob, draft.filename)
    window.$message.success('Editable Outlook draft downloaded.')
  } catch (cause) {
    emit('error', cause)
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <n-card title="Notification delivery" size="small">
    <n-space vertical>
      <n-flex class="tracking-action-row">
        <n-select
          v-model:value="eventType"
          :options="eventOptions"
          :disabled="disabled || loading"
        />
        <n-button type="primary" :disabled="actionDisabled" @click="confirmSend">
          Send automatically
        </n-button>
        <n-button secondary :disabled="actionDisabled" :loading="loading" @click="downloadDraft">
          Download Outlook draft
        </n-button>
      </n-flex>
      <n-alert v-if="selectedState" :type="stateAlertType" :bordered="false">
        <template #header>{{ stateHeader }}</template>
        {{ selectedState.detail }}
        <br />
        Policy v{{ selectedState.policy_version }} routes
        {{ selectedState.primary_recipient_count }} primary and
        {{ selectedState.escalation_recipient_count }} escalation recipient(s).
      </n-alert>
      <n-alert v-if="!configured" type="warning" :bordered="false">
        Save tracking preferences before sending or downloading a draft.
      </n-alert>
      <n-alert
        v-else-if="selectedState && !selectedState.recipient_count"
        type="warning"
        :bordered="false"
      >
        No current ATA contact matches this event's project policy roles.
      </n-alert>
      <n-text depth="3">
        The .msg draft includes recipients, subject, and the full HTML template. Open it in Outlook
        to review, edit, and send manually.
      </n-text>
    </n-space>
  </n-card>
</template>
