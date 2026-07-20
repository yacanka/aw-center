<template>
  <n-card title="JIRA readiness" size="small" embedded>
    <n-space vertical>
      <n-alert type="info" :bordered="false">
        Uses the temporary session only to inspect the live Task create screen. The credential is
        never saved.
      </n-alert>
      <n-input
        :value="sessionId"
        type="password"
        show-password-on="click"
        :input-props="{
          autocomplete: 'one-time-code',
          name: 'temporary-jira-session'
        }"
        placeholder="Temporary JIRA session ID"
        @update:value="emit('update:sessionId', $event)"
      />
      <n-alert v-if="dirty" type="warning" :bordered="false">
        Save the current draft changes before checking JIRA requirements.
      </n-alert>
      <n-button
        secondary
        :loading="busy"
        :disabled="sessionId.length < 8 || dirty"
        @click="emit('check')"
      >
        Check connection and requirements
      </n-button>
      <template v-if="result">
        <n-alert :type="result.ready ? 'success' : 'warning'" :bordered="false">
          <template v-if="result.ready">
            {{ result.project_key }} {{ result.issue_type }} is ready for safe publication.
          </template>
          <template v-else>
            Complete the supported fields below, save the draft, and run the check again.
          </template>
        </n-alert>
        <n-form v-if="result.fields.length" label-placement="top" :disabled="locked">
          <n-form-item v-for="field in result.fields" :key="field.id" :label="field.name">
            <jira-field-input
              :field="field"
              :model-value="extraFields[field.id]"
              @update:model-value="emit('update-field', field.id, $event)"
            />
          </n-form-item>
        </n-form>
        <n-alert v-if="result.unsupported_fields.length" type="error" :bordered="false">
          Unsupported required fields: {{ fieldNames(result.unsupported_fields) }}. Ask a JIRA
          administrator to add a default or use a supported field type.
        </n-alert>
        <n-alert v-if="result.invalid_fields.length" type="error" :bordered="false">
          Values no longer accepted by JIRA: {{ fieldNames(result.invalid_fields) }}.
        </n-alert>
        <n-alert v-for="warning in result.warnings" :key="warning" type="warning" :bordered="false">
          {{ warning }}
        </n-alert>
      </template>
    </n-space>
  </n-card>
</template>

<script setup lang="ts">
import JiraFieldInput from '@/components/jira/JiraFieldInput.vue'
import type { JiraFieldValue } from '@/models/jira'
import type { JiraIssueDraftPreflight, JiraPreflightIdentity } from '@/services/jiraIssueDrafts'

defineProps<{
  sessionId: string
  busy: boolean
  dirty: boolean
  locked: boolean
  result: JiraIssueDraftPreflight | null
  extraFields: Record<string, JiraFieldValue>
}>()

const emit = defineEmits<{
  'update:sessionId': [value: string]
  'update-field': [identifier: string, value: JiraFieldValue]
  check: []
}>()

function fieldNames(fields: JiraPreflightIdentity[]): string {
  return fields.map((field) => `${field.name} (${field.id})`).join(', ')
}
</script>
