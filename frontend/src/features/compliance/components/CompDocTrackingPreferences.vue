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
  <n-card title="Notification recipients" size="small">
    <n-space vertical>
      <n-select
        :value="tracking.responsible_mode"
        :options="[
          { label: 'All panel responsibles', value: 'automatic' },
          { label: 'Selected panel responsibles', value: 'custom' }
        ]"
        :disabled="disabled"
        @update:value="update({ responsible_mode: $event })"
      />
      <n-select
        v-if="tracking.responsible_mode === 'custom'"
        :value="tracking.responsible_person_ids"
        :options="
          tracking.responsible_options.map((person) => ({
            label: `${person.name} · ${person.email}`,
            value: person.id
          }))
        "
        :disabled="disabled"
        multiple
        filterable
        placeholder="Choose panel responsibles"
        @update:value="update({ responsible_person_ids: $event })"
      />
      <n-text v-if="!tracking.responsible_options.length" depth="3">
        This document's panel has no responsible person with an email address.
      </n-text>
    </n-space>
  </n-card>

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
