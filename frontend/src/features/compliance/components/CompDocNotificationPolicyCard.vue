<script setup lang="ts">
import { ref, watch } from 'vue'
import { formatApiError } from '@/shared/api/apiError'
import {
  cloneCompDocNotificationRules,
  fetchCompDocNotificationPolicy,
  saveCompDocNotificationPolicy,
  type CompDocNotificationPolicy,
  type CompDocNotificationRules
} from '@/features/compliance/api/compdocNotificationPolicy'
import {
  formatTrackingTimestamp,
  TRACKING_EVENT_OPTIONS,
  type CompDocNotificationEvent
} from '@/features/compliance/api/compdocTracking'

const props = defineProps<{ project: string }>()
const emit = defineEmits<{ saved: [] }>()
const policy = ref<CompDocNotificationPolicy | null>(null)
const draft = ref<CompDocNotificationRules>({})
const changeNote = ref('')
const loading = ref(false)
const saving = ref(false)
const editing = ref(false)
const error = ref('')
let loadSequence = 0

watch(() => props.project, resetProject, { immediate: true })

function resetProject() {
  editing.value = false
  draft.value = {}
  changeNote.value = ''
  void load()
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
  if (!policy.value || !policy.value.allowed_actions.manage) return
  draft.value = cloneCompDocNotificationRules(policy.value.event_rules)
  changeNote.value = ''
  editing.value = true
}

function setEnabled(event: CompDocNotificationEvent, enabled: boolean) {
  draft.value = { ...draft.value, [event]: { enabled } }
}

async function save() {
  if (!policy.value || changeNote.value.trim().length < 3) return
  saving.value = true
  error.value = ''
  try {
    policy.value = await saveCompDocNotificationPolicy(props.project, {
      version: policy.value.version,
      change_note: changeNote.value.trim(),
      event_rules: draft.value
    })
    editing.value = false
    emit('saved')
    window.$message.success(`Notification policy v${policy.value.version} published.`)
  } catch (cause) {
    error.value = formatApiError(cause)
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <n-card title="Project notification policy" size="small">
    <n-spin :show="loading || saving">
      <n-space v-if="policy" vertical>
        <n-flex justify="space-between" align="center">
          <n-text>
            Version {{ policy.version }} ·
            {{ policy.updated_at ? formatTrackingTimestamp(policy.updated_at) : 'not configured' }}
          </n-text>
          <n-button
            v-if="policy.allowed_actions.manage && !editing"
            size="small"
            secondary
            @click="startEditing"
          >
            Manage policy
          </n-button>
        </n-flex>
        <n-alert v-if="error" type="error" :bordered="false">{{ error }}</n-alert>
        <n-list>
          <n-list-item v-for="event in TRACKING_EVENT_OPTIONS" :key="event.value">
            <n-flex justify="space-between" align="center">
              <n-text>{{ event.label }}</n-text>
              <n-switch
                v-if="editing"
                :value="draft[event.value]?.enabled ?? true"
                @update:value="setEnabled(event.value, $event)"
              />
              <n-tag v-else size="small">
                {{ policy.event_rules[event.value]?.enabled === false ? 'Disabled' : 'Enabled' }}
              </n-tag>
            </n-flex>
          </n-list-item>
        </n-list>
        <template v-if="editing">
          <n-input
            v-model:value="changeNote"
            maxlength="255"
            show-count
            placeholder="Reason for this policy revision"
          />
          <n-flex justify="end">
            <n-button @click="editing = false">Cancel</n-button>
            <n-button
              type="primary"
              :disabled="changeNote.trim().length < 3"
              :loading="saving"
              @click="save"
            >
              Publish revision
            </n-button>
          </n-flex>
        </template>
      </n-space>
      <n-alert v-else-if="error" type="error" :bordered="false">{{ error }}</n-alert>
    </n-spin>
  </n-card>
</template>
