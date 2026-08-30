<script setup lang="ts">
import type {
  CompDocNotificationEvent,
  CompDocTracking,
  CompDocTrackingPreferenceValues
} from '@/features/compliance/api/compdocTracking'
import { TRACKING_EVENT_OPTIONS } from '@/features/compliance/api/compdocTracking'
import CompDocNotificationPolicyCard from './CompDocNotificationPolicyCard.vue'

const props = defineProps<{
  tracking: CompDocTracking
  disabled: boolean
  project: string
}>()
const emit = defineEmits<{
  change: [value: CompDocTrackingPreferenceValues]
  'policy-saved': []
}>()

function update(patch: Partial<CompDocTrackingPreferenceValues>) {
  emit('change', {
    responsible_mode: props.tracking.responsible_mode,
    responsible_person_ids: props.tracking.responsible_person_ids,
    notification_enabled: props.tracking.notification_enabled,
    notification_events: props.tracking.notification_events,
    ...patch
  })
}

function updateEvents(value: CompDocNotificationEvent[]) {
  update({ notification_events: value })
}
</script>

<template>
  <n-card title="Automatic alerts" size="small">
    <n-space vertical>
      <n-flex justify="space-between" align="center">
        <n-text>Enable notifications for this document</n-text>
        <n-switch
          :value="tracking.notification_enabled"
          :disabled="disabled"
          @update:value="update({ notification_enabled: $event })"
        />
      </n-flex>
      <n-select
        :value="tracking.notification_events"
        :options="TRACKING_EVENT_OPTIONS"
        :disabled="disabled || !tracking.notification_enabled"
        multiple
        placeholder="Choose alert types"
        @update:value="updateEvents"
      />
      <n-text depth="3">
        Messages are deduplicated by document, event, and revision/target date.
      </n-text>
    </n-space>
  </n-card>

  <CompDocNotificationPolicyCard :project="project" @saved="emit('policy-saved')" />
</template>
