<script setup lang="ts">
import { computed } from 'vue'
import type {
  CompDocNotificationEvent,
  CompDocTracking,
  CompDocTrackingUpdate,
  ResponsibleMode
} from '@/services/compdocTracking'
import CompDocNotificationPolicyCard from './CompDocNotificationPolicyCard.vue'

const props = defineProps<{
  tracking: CompDocTracking
  disabled: boolean
  project: string
}>()
const emit = defineEmits<{
  change: [value: CompDocTrackingUpdate]
  'policy-saved': []
}>()
const modeOptions = [
  { value: 'automatic', label: 'Automatic — follow the ATA panel' },
  { value: 'custom', label: 'Custom — choose from this ATA panel' }
]
const personOptions = computed(() =>
  props.tracking.candidate_responsibles.map((person) => ({
    value: person.id,
    label: `${person.name} · ${person.title} · ${person.email}`
  }))
)

function update(patch: Partial<CompDocTrackingUpdate>) {
  emit('change', {
    responsible_mode: props.tracking.responsible_mode,
    responsible_person_ids: props.tracking.responsible_person_ids,
    notification_enabled: props.tracking.notification_enabled,
    notification_events: props.tracking.notification_events,
    ...patch
  })
}

function updateMode(value: ResponsibleMode) {
  const ids =
    value === 'automatic'
      ? props.tracking.candidate_responsibles.map((person) => person.id)
      : props.tracking.responsible_person_ids
  update({ responsible_mode: value, responsible_person_ids: ids })
}

function updateEvents(value: CompDocNotificationEvent[]) {
  update({ notification_events: value })
}
</script>

<template>
  <n-card title="Responsible team" size="small">
    <n-space vertical>
      <n-text depth="3">
        ATA {{ tracking.document.ata || 'not assigned' }} currently resolves to
        {{ tracking.candidate_responsibles.length }} organization contact(s).
      </n-text>
      <n-select
        :value="tracking.responsible_mode"
        :options="modeOptions"
        :disabled="disabled"
        @update:value="updateMode"
      />
      <n-select
        :value="tracking.responsible_person_ids"
        :options="personOptions"
        :disabled="disabled || tracking.responsible_mode === 'automatic'"
        multiple
        filterable
        max-tag-count="responsive"
        placeholder="Select responsible contacts"
        @update:value="update({ responsible_person_ids: $event })"
      />
      <n-alert v-if="!personOptions.length" type="warning" :bordered="false">
        No responsible is assigned to this ATA chapter. Add one in Organizations before enabling
        alerts.
      </n-alert>
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
        :options="tracking.event_options"
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
