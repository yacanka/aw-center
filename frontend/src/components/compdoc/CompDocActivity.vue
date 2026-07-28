<script setup lang="ts">
import { ref, watch } from 'vue'
import type { ICompDoc, ICompDocActivity } from '@/models/compdocs'
import { statusOptions } from '@/services/compdocCatalog'
import {
  fetchCompdocActivity,
  transitionCompdoc,
  type TransitionRequest
} from '@/services/compdocLifecycle'
import { isoToTurkishDateTime } from '@/utils/time'
import { formatApiError } from '@/services/apiError'

const props = defineProps<{
  show: boolean
  project: string
  document: ICompDoc
  canEdit: boolean
}>()
const emit = defineEmits<{ changed: [] }>()
const activity = ref<ICompDocActivity[]>([])
const loading = ref(false)
const saving = ref(false)
const transitionVisible = ref(false)
const transition = ref<TransitionRequest>(emptyTransition())

watch(
  () => [props.show, props.document.id, props.document.source_history_id],
  ([show]) => {
    if (!show) return
    transition.value = emptyTransition()
    void loadActivity()
  },
  { immediate: true }
)

function emptyTransition(): TransitionRequest {
  return {
    source_history_id: props.document.source_history_id || 0,
    status: props.document.status || 'unknown',
    effective_date: new Date().toISOString().slice(0, 10),
    next_action_due_date: props.document.next_action_due_date,
    reason: ''
  }
}

async function loadActivity() {
  if (!props.document.id) return
  loading.value = true
  try {
    activity.value = await fetchCompdocActivity(props.project, props.document.id)
  } catch (error) {
    window.$message.error(formatApiError(error))
  } finally {
    loading.value = false
  }
}

async function submitTransition() {
  if (!props.document.id || !transition.value.source_history_id) {
    window.$message.error('Reload the document before recording a transition.')
    return
  }
  if (transition.value.reason.trim().length < 3) {
    window.$message.warning('Enter a meaningful transition reason.')
    return
  }
  saving.value = true
  try {
    await transitionCompdoc(props.project, props.document.id, transition.value)
    window.$message.success('Lifecycle transition recorded.')
    transitionVisible.value = false
    transition.value = emptyTransition()
    await loadActivity()
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
    <n-flex justify="space-between" align="center">
      <n-text strong>Activity</n-text>
      <n-button v-if="canEdit" size="small" @click="transitionVisible = !transitionVisible">
        Record transition
      </n-button>
    </n-flex>
    <n-card v-if="transitionVisible" size="small" embedded>
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
          <n-form-item-gi label="Reason">
            <n-input v-model:value="transition.reason" maxlength="255" show-count />
          </n-form-item-gi>
        </n-grid>
        <n-button type="primary" :loading="saving" @click="submitTransition">
          Save transition
        </n-button>
      </n-form>
    </n-card>
    <n-spin :show="loading">
      <n-timeline v-if="activity.length">
        <n-timeline-item
          v-for="(item, index) in activity"
          :key="`${item.occurred_at}-${index}`"
          :title="item.actor || 'System'"
          :content="
            item.type === 'workflow'
              ? `${item.previous_status || 'Unknown'} → ${item.status}: ${item.reason}`
              : item.type === 'history'
                ? `${item.reason} (${item.changes?.map((change) => change.field).join(', ') || 'record'})`
                : `${item.type}: ${item.status} — ${item.reason}`
          "
          :time="isoToTurkishDateTime(item.occurred_at)"
        />
      </n-timeline>
      <n-empty v-else-if="!loading" description="No recorded activity." size="small" />
    </n-spin>
  </section>
</template>
