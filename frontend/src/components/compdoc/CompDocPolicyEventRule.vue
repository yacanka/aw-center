<script setup lang="ts">
import { computed } from 'vue'
import type { CompDocNotificationRule } from '@/services/compdocNotificationPolicy'

const props = defineProps<{
  eventLabel: string
  rule: CompDocNotificationRule
  roleOptions: Array<{ value: string; label: string }>
  disabled: boolean
}>()
const emit = defineEmits<{ change: [value: CompDocNotificationRule] }>()
const reminderOptions = [
  { value: 0, label: 'Send once per evidence' },
  { value: 24, label: 'Repeat every day' },
  { value: 48, label: 'Repeat every 2 days' },
  { value: 72, label: 'Repeat every 3 days' },
  { value: 168, label: 'Repeat every week' }
]
const primaryOptions = computed(() =>
  props.roleOptions.filter((option) => !props.rule.escalation_titles.includes(option.value))
)
const escalationOptions = computed(() =>
  props.roleOptions.filter((option) => !props.rule.primary_titles.includes(option.value))
)

function update(patch: Partial<CompDocNotificationRule>) {
  emit('change', { ...props.rule, ...patch })
}

function updatePrimary(values: string[]) {
  const escalation = values.length
    ? props.rule.escalation_titles.filter((title) => !values.includes(title))
    : []
  update({ primary_titles: values, escalation_titles: escalation })
}

function updateEscalation(values: string[]) {
  const delay = values.length ? props.rule.escalate_after_hours || 24 : 0
  update({ escalation_titles: values, escalate_after_hours: delay })
}
</script>

<template>
  <n-card :title="eventLabel" size="small" embedded>
    <n-grid cols="1 620:2" :x-gap="12">
      <n-form-item-gi label="Reminder cadence">
        <n-select
          :value="rule.reminder_interval_hours"
          :options="reminderOptions"
          :disabled="disabled"
          @update:value="update({ reminder_interval_hours: $event })"
        />
      </n-form-item-gi>
      <n-form-item-gi label="Retry failed delivery after">
        <n-input-number
          :value="rule.failure_retry_hours"
          :min="1"
          :max="720"
          :disabled="disabled"
          @update:value="update({ failure_retry_hours: $event || 1 })"
        >
          <template #suffix>hours</template>
        </n-input-number>
      </n-form-item-gi>
      <n-form-item-gi label="Primary roles">
        <n-select
          :value="rule.primary_titles"
          :options="primaryOptions"
          :disabled="disabled"
          multiple
          clearable
          placeholder="All ATA roles"
          @update:value="updatePrimary"
        />
      </n-form-item-gi>
      <n-form-item-gi label="Escalation roles">
        <n-select
          :value="rule.escalation_titles"
          :options="escalationOptions"
          :disabled="disabled || !rule.primary_titles.length"
          multiple
          clearable
          placeholder="No escalation"
          @update:value="updateEscalation"
        />
      </n-form-item-gi>
      <n-form-item-gi v-if="rule.escalation_titles.length" label="Escalate after">
        <n-input-number
          :value="rule.escalate_after_hours"
          :min="0"
          :max="8760"
          :disabled="disabled"
          @update:value="update({ escalate_after_hours: $event || 0 })"
        >
          <template #suffix>hours</template>
        </n-input-number>
      </n-form-item-gi>
    </n-grid>
    <n-text depth="3">
      Empty primary roles include every current ATA responsible. Escalation recipients are added as
      CC after the configured delay.
    </n-text>
  </n-card>
</template>
