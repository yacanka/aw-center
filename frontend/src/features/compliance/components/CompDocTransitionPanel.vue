<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { ICompDoc } from '@/features/compliance/models/compdocs'
import { workflowStatusOptions } from '@/features/compliance/api/compdocCatalog'
import {
  transitionCompdoc,
  type TransitionRequest
} from '@/features/compliance/api/compdocLifecycle'
import { formatApiError } from '@/shared/api/apiError'

const props = defineProps<{
  show: boolean
  project: string
  document: ICompDoc
}>()
const emit = defineEmits<{ changed: [] }>()
const saving = ref(false)
const transition = ref<TransitionRequest>(emptyTransition())
const currentWorkflowStatus = computed(() =>
  props.document.status === 'delayed' ? 'to_be_issued' : props.document.status
)
const availableStatuses = computed(() =>
  workflowStatusOptions.filter((option) => option.value !== currentWorkflowStatus.value)
)
const canSubmit = computed(
  () =>
    Boolean(props.document.id && transition.value.version) &&
    Boolean(transition.value.status) &&
    Boolean(transition.value.effective_date) &&
    transition.value.status !== currentWorkflowStatus.value
)

watch(
  () => [props.show, props.document.id, props.document.version],
  ([show]) => {
    if (show) transition.value = emptyTransition()
  },
  { immediate: true }
)

function emptyTransition(): TransitionRequest {
  return {
    version: props.document.version || 0,
    status: '',
    effective_date: localDate(),
    next_action_due_date: props.document.next_action_due_date,
    reason: ''
  }
}

function localDate(): string {
  const today = new Date()
  const year = today.getFullYear()
  const month = String(today.getMonth() + 1).padStart(2, '0')
  const day = String(today.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

async function submitTransition(): Promise<void> {
  if (!props.document.id || !transition.value.version) {
    window.$message.error('Reload the document before recording a transition.')
    return
  }
  saving.value = true
  try {
    await transitionCompdoc(props.project, props.document.id, transition.value)
    window.$message.success('Lifecycle transition recorded.')
    transition.value = emptyTransition()
    emit('changed')
  } catch (error) {
    window.$message.error(formatApiError(error))
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <section class="workspace-section">
    <n-alert type="info" :show-icon="false">
      Status changes are recorded as immutable workflow events.
    </n-alert>
    <n-form label-placement="top">
      <n-grid responsive="screen" cols="1 s:2" :x-gap="12">
        <n-form-item-gi label="New status">
          <n-select
            v-model:value="transition.status"
            :options="availableStatuses"
            placeholder="Select a new status"
          />
        </n-form-item-gi>
        <n-form-item-gi label="Effective date">
          <n-date-picker v-model:formatted-value="transition.effective_date" type="date" />
        </n-form-item-gi>
        <n-form-item-gi label="Next action due">
          <n-date-picker
            v-model:formatted-value="transition.next_action_due_date"
            type="date"
            clearable
          />
        </n-form-item-gi>
        <n-form-item-gi label="Reason (optional)">
          <n-input
            v-model:value="transition.reason"
            maxlength="255"
            show-count
            placeholder="Optional transition explanation"
          />
        </n-form-item-gi>
      </n-grid>
      <n-button type="primary" :loading="saving" :disabled="!canSubmit" @click="submitTransition">
        Save transition
      </n-button>
    </n-form>
  </section>
</template>
