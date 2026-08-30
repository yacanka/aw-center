<script setup lang="ts">
import { ref, watch } from 'vue'
import type { ICompDoc } from '@/features/compliance/models/compdocs'
import {
  fetchCompdocWork,
  updateCompdocWork,
  type CompdocWork
} from '@/features/compliance/api/compdocLifecycle'
import { formatApiError } from '@/shared/api/apiError'

const props = defineProps<{
  show: boolean
  project: string
  document: ICompDoc
  canEdit: boolean
}>()
const emit = defineEmits<{ changed: [] }>()
const work = ref<CompdocWork | null>(null)
const reason = ref('')
const loading = ref(false)

watch(
  () => [props.show, props.document.id],
  ([show]) => {
    if (show) void load()
  },
  { immediate: true }
)

async function load() {
  if (!props.document.id) return
  loading.value = true
  try {
    work.value = await fetchCompdocWork(props.project, props.document.id)
  } catch (error) {
    window.$message.error(formatApiError(error))
  } finally {
    loading.value = false
  }
}

async function save() {
  if (!props.document.id || !work.value) return
  loading.value = true
  try {
    work.value = await updateCompdocWork(props.project, props.document.id, {
      version: work.value.version,
      owner: work.value.owner,
      owner_group: work.value.owner_group,
      next_action_due_date: work.value.next_action_due_date,
      reason: reason.value
    })
    reason.value = ''
    window.$message.success('Document ownership updated.')
    emit('changed')
  } catch (error) {
    window.$message.error(formatApiError(error))
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <section class="workspace-section">
    <n-spin :show="loading">
      <n-grid v-if="work" responsive="screen" cols="1 s:2" :x-gap="12">
        <n-form-item-gi label="AW Center owner">
          <n-input :value="work.owner_username || 'Unassigned'" disabled />
        </n-form-item-gi>
        <n-form-item-gi label="Owner team">
          <n-input :value="work.owner_group_name || 'Unassigned'" disabled />
        </n-form-item-gi>
        <n-form-item-gi label="Next action due">
          <n-date-picker
            v-model:formatted-value="work.next_action_due_date"
            type="date"
            :disabled="!canEdit"
            clearable
          />
        </n-form-item-gi>
        <n-form-item-gi v-if="canEdit" label="Change reason (optional)">
          <n-input
            v-model:value="reason"
            maxlength="255"
            show-count
            placeholder="Optional ownership explanation"
          />
        </n-form-item-gi>
      </n-grid>
      <n-button v-if="canEdit && work" size="small" type="primary" @click="save">
        Save ownership
      </n-button>
    </n-spin>
    <n-text depth="3">Legacy/external responsible: {{ document.responsible || 'None' }}</n-text>
  </section>
</template>
