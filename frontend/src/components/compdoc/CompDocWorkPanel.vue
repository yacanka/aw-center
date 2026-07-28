<script setup lang="ts">
import { ref, watch } from 'vue'
import type { ICompDoc } from '@/models/compdocs'
import {
  fetchCompdocAssignees,
  fetchCompdocWork,
  updateCompdocWork,
  type CompdocAssignees,
  type CompdocWork
} from '@/services/compdocLifecycle'
import { formatApiError } from '@/services/apiError'

const props = defineProps<{
  show: boolean
  project: string
  document: ICompDoc
  canEdit: boolean
}>()
const emit = defineEmits<{ changed: [] }>()
const work = ref<CompdocWork | null>(null)
const assignees = ref<CompdocAssignees>({ users: [], groups: [] })
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
    const requests: [Promise<CompdocWork>, Promise<CompdocAssignees> | null] = [
      fetchCompdocWork(props.project, props.document.id),
      props.canEdit ? fetchCompdocAssignees(props.project) : null
    ]
    work.value = await requests[0]
    if (requests[1]) assignees.value = await requests[1]
  } catch (error) {
    window.$message.error(formatApiError(error))
  } finally {
    loading.value = false
  }
}

async function save() {
  if (!props.document.id || !work.value || reason.value.trim().length < 3) {
    window.$message.warning('Enter a meaningful assignment reason.')
    return
  }
  loading.value = true
  try {
    work.value = await updateCompdocWork(props.project, props.document.id, {
      source_history_id: work.value.source_history_id,
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
    <n-text strong>Ownership & next action</n-text>
    <n-spin :show="loading">
      <n-grid v-if="work" responsive="screen" cols="1 s:2" :x-gap="12">
        <n-form-item-gi label="AW Center owner">
          <n-select
            v-model:value="work.owner"
            :options="assignees.users.map((item) => ({ label: item.username, value: item.id }))"
            :disabled="!canEdit"
            clearable
          />
        </n-form-item-gi>
        <n-form-item-gi label="Owner team">
          <n-select
            v-model:value="work.owner_group"
            :options="assignees.groups.map((item) => ({ label: item.name, value: item.id }))"
            :disabled="!canEdit"
            clearable
          />
        </n-form-item-gi>
        <n-form-item-gi label="Next action due">
          <n-date-picker
            v-model:formatted-value="work.next_action_due_date"
            type="date"
            :disabled="!canEdit"
            clearable
          />
        </n-form-item-gi>
        <n-form-item-gi v-if="canEdit" label="Change reason">
          <n-input v-model:value="reason" maxlength="255" show-count />
        </n-form-item-gi>
      </n-grid>
      <n-button v-if="canEdit && work" size="small" type="primary" @click="save">
        Save ownership
      </n-button>
    </n-spin>
    <n-text depth="3">Legacy/external responsible: {{ document.responsible || 'None' }}</n-text>
  </section>
</template>
