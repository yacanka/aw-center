<script setup lang="ts">
import { ref, watch } from 'vue'
import { formatApiError } from '@/services/apiError'
import {
  cloneCompDocNotificationRules,
  fetchCompDocNotificationPolicy,
  saveCompDocNotificationPolicy,
  type CompDocNotificationPolicy,
  type CompDocNotificationRule,
  type CompDocNotificationRules
} from '@/services/compdocNotificationPolicy'
import { formatTrackingTimestamp, type CompDocNotificationEvent } from '@/services/compdocTracking'
import CompDocPolicyEventRule from './CompDocPolicyEventRule.vue'

const props = defineProps<{ project: string }>()
const emit = defineEmits<{ saved: [] }>()
const policy = ref<CompDocNotificationPolicy | null>(null)
const draft = ref<CompDocNotificationRules | null>(null)
const changeNote = ref('')
const loading = ref(false)
const saving = ref(false)
const editing = ref(false)
const error = ref('')
let loadSequence = 0

watch(() => props.project, resetProject, { immediate: true })

function resetProject() {
  editing.value = false
  draft.value = null
  changeNote.value = ''
  load()
}

async function load() {
  const sequence = ++loadSequence
  loading.value = true
  error.value = ''
  try {
    const response = await fetchCompDocNotificationPolicy(props.project)
    if (sequence === loadSequence) policy.value = response
  } catch (cause) {
    if (sequence === loadSequence) error.value = formatApiError(cause)
  } finally {
    if (sequence === loadSequence) loading.value = false
  }
}

function startEditing() {
  if (!policy.value?.can_manage) return
  draft.value = cloneCompDocNotificationRules(policy.value.rules)
  changeNote.value = ''
  editing.value = true
}

function cancelEditing() {
  draft.value = null
  editing.value = false
  error.value = ''
}

function updateRule(event: CompDocNotificationEvent, rule: CompDocNotificationRule) {
  if (!draft.value) return
  draft.value = { ...draft.value, [event]: rule }
}

async function save() {
  if (!policy.value || !draft.value || changeNote.value.trim().length < 3) return
  saving.value = true
  error.value = ''
  try {
    policy.value = await saveCompDocNotificationPolicy(props.project, {
      expected_version: policy.value.version,
      change_note: changeNote.value.trim(),
      rules: draft.value
    })
    cancelEditing()
    emit('saved')
    window.$message.success(`Notification policy v${policy.value.version} published.`)
  } catch (cause) {
    error.value = formatApiError(cause)
  } finally {
    saving.value = false
  }
}

function cadence(rule: CompDocNotificationRule) {
  return rule.reminder_interval_hours
    ? `every ${rule.reminder_interval_hours}h`
    : 'once per evidence'
}

function roles(values: string[]) {
  return values.length ? values.join(', ') : 'all ATA roles'
}
</script>

<template>
  <n-card title="Project notification policy" size="small">
    <n-spin :show="loading || saving">
      <n-space v-if="policy" vertical>
        <n-flex justify="space-between" align="center">
          <n-space align="center">
            <n-tag :type="policy.configured ? 'success' : 'default'">
              {{ policy.configured ? `Version ${policy.version}` : 'Safe default' }}
            </n-tag>
            <n-text depth="3">
              {{
                policy.updated_at
                  ? `${policy.updated_by} · ${formatTrackingTimestamp(policy.updated_at)}`
                  : 'No project-specific revision yet'
              }}
            </n-text>
          </n-space>
          <n-button
            v-if="policy.can_manage && !editing"
            size="small"
            secondary
            @click="startEditing"
          >
            Manage policy
          </n-button>
        </n-flex>

        <n-alert v-if="error" type="error" :bordered="false">
          {{ error }}
          <template #action><n-button size="tiny" @click="load">Reload</n-button></template>
        </n-alert>

        <template v-if="editing && draft">
          <CompDocPolicyEventRule
            v-for="event in policy.event_options"
            :key="event.value"
            :event-label="event.label"
            :rule="draft[event.value]"
            :role-options="policy.role_options"
            :disabled="saving"
            @change="updateRule(event.value, $event)"
          />
          <n-form-item label="Reason for this revision" :show-feedback="false">
            <n-input
              v-model:value="changeNote"
              maxlength="255"
              show-count
              placeholder="Describe the operational reason"
            />
          </n-form-item>
          <n-flex justify="end">
            <n-button :disabled="saving" @click="cancelEditing">Cancel</n-button>
            <n-button
              type="primary"
              :disabled="changeNote.trim().length < 3"
              :loading="saving"
              @click="save"
            >
              Publish new revision
            </n-button>
          </n-flex>
        </template>

        <n-collapse v-else>
          <n-collapse-item title="Policy details" name="details">
            <n-list>
              <n-list-item v-for="event in policy.event_options" :key="event.value">
                <n-thing :title="event.label">
                  <n-text depth="3">
                    {{ cadence(policy.rules[event.value]) }} · failed retry
                    {{ policy.rules[event.value].failure_retry_hours }}h · primary
                    {{ roles(policy.rules[event.value].primary_titles) }} · escalation
                    {{ policy.rules[event.value].escalation_titles.join(', ') || 'none' }}
                  </n-text>
                </n-thing>
              </n-list-item>
            </n-list>
          </n-collapse-item>
          <n-collapse-item v-if="policy.history.length" title="Revision history" name="history">
            <n-list>
              <n-list-item v-for="revision in policy.history" :key="revision.version">
                <n-text>v{{ revision.version }} · {{ revision.change_note }}</n-text>
                <template #suffix>
                  <n-text depth="3">{{ formatTrackingTimestamp(revision.created_at) }}</n-text>
                </template>
              </n-list-item>
            </n-list>
          </n-collapse-item>
        </n-collapse>
      </n-space>
      <n-alert v-else-if="error" type="error" :bordered="false">{{ error }}</n-alert>
    </n-spin>
  </n-card>
</template>
