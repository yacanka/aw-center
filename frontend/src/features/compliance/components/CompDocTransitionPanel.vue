<script setup lang="ts">
import { ref, watch } from 'vue'
import type { ICompDoc } from '@/features/compliance/models/compdocs'
import { statusOptions } from '@/features/compliance/api/compdocCatalog'
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
    status: props.document.status || 'unknown',
    effective_date: new Date().toISOString().slice(0, 10),
    next_action_due_date: props.document.next_action_due_date,
    reason: ''
  }
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
          <n-select v-model:value="transition.status" :options="statusOptions" />
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
      <n-button type="primary" :loading="saving" @click="submitTransition">
        Save transition
      </n-button>
    </n-form>
  </section>
</template>
