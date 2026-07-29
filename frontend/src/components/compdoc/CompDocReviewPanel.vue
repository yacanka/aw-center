<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { ICompDoc } from '@/models/compdocs'
import { useUserStore } from '@/stores/user'
import {
  createCompdocReview,
  decideCompdocReview,
  fetchCompdocAssignees,
  fetchCompdocReviews,
  type CompdocAssignees,
  type CompdocReview
} from '@/services/compdocLifecycle'
import { formatApiError } from '@/services/apiError'

const props = defineProps<{
  show: boolean
  project: string
  document: ICompDoc
  canEdit: boolean
}>()
const emit = defineEmits<{ changed: [] }>()
const userStore = useUserStore()
const reviews = ref<CompdocReview[]>([])
const assignees = ref<CompdocAssignees>({ users: [], groups: [] })
const loading = ref(false)
const formVisible = ref(false)
const form = ref({
  kind: 'review' as 'review' | 'approval',
  assignee: null as number | null,
  due_date: null as string | null,
  request_note: ''
})
const decisionNotes = ref<Record<string, string>>({})
const userId = computed(() => userStore.getUser.id)

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
    reviews.value = await fetchCompdocReviews(props.project, props.document.id)
    if (props.canEdit) assignees.value = await fetchCompdocAssignees(props.project)
  } catch (error) {
    window.$message.error(formatApiError(error))
  } finally {
    loading.value = false
  }
}

async function createTask() {
  if (!props.document.id || !props.document.source_history_id) return
  if (!form.value.assignee || form.value.request_note.trim().length < 3) {
    window.$message.warning('Select an assignee and enter a request note.')
    return
  }
  loading.value = true
  try {
    await createCompdocReview(props.project, props.document.id, {
      ...form.value,
      source_history_id: props.document.source_history_id
    })
    formVisible.value = false
    form.value.request_note = ''
    await load()
    emit('changed')
  } catch (error) {
    window.$message.error(formatApiError(error))
  } finally {
    loading.value = false
  }
}

async function decide(task: CompdocReview, status: 'approved' | 'changes_requested' | 'cancelled') {
  if (!props.document.id || (decisionNotes.value[task.id] || '').trim().length < 3) {
    window.$message.warning('Enter a decision note.')
    return
  }
  loading.value = true
  try {
    await decideCompdocReview(
      props.project,
      props.document.id,
      task.id,
      status,
      decisionNotes.value[task.id]
    )
    await load()
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
    <n-flex v-if="canEdit" justify="flex-end">
      <n-button size="small" @click="formVisible = !formVisible">Request decision</n-button>
    </n-flex>
    <n-card v-if="formVisible" size="small" embedded>
      <n-space vertical>
        <n-select
          v-model:value="form.kind"
          :options="[
            { label: 'Review', value: 'review' },
            { label: 'Approval', value: 'approval' }
          ]"
        />
        <n-select
          v-model:value="form.assignee"
          :options="assignees.users.map((item) => ({ label: item.username, value: item.id }))"
          placeholder="Assignee"
          filterable
        />
        <n-date-picker v-model:formatted-value="form.due_date" type="date" clearable />
        <n-input
          v-model:value="form.request_note"
          type="textarea"
          maxlength="500"
          show-count
          placeholder="Request note"
        />
        <n-button type="primary" @click="createTask">Create task</n-button>
      </n-space>
    </n-card>
    <n-spin :show="loading">
      <n-card v-for="task in reviews" :key="task.id" size="small">
        <n-flex justify="space-between">
          <n-text>{{ task.kind }} · {{ task.assignee_username }}</n-text>
          <n-tag size="small">{{ task.status }}</n-tag>
        </n-flex>
        <n-text depth="3">{{ task.request_note }}</n-text>
        <n-space v-if="task.status === 'pending' && task.assignee === userId" vertical>
          <n-input
            v-model:value="decisionNotes[task.id]"
            maxlength="500"
            placeholder="Decision note"
          />
          <n-flex>
            <n-button size="small" type="success" @click="decide(task, 'approved')">
              Approve
            </n-button>
            <n-button size="small" type="warning" @click="decide(task, 'changes_requested')">
              Request changes
            </n-button>
          </n-flex>
        </n-space>
        <n-input
          v-if="task.status === 'pending' && canEdit && task.assignee !== userId"
          v-model:value="decisionNotes[task.id]"
          maxlength="500"
          placeholder="Cancellation reason"
        />
        <n-button
          v-if="task.status === 'pending' && canEdit"
          size="small"
          quaternary
          type="error"
          @click="decide(task, 'cancelled')"
        >
          Cancel task
        </n-button>
      </n-card>
      <n-empty v-if="!loading && !reviews.length" description="No review tasks." size="small" />
    </n-spin>
  </section>
</template>
