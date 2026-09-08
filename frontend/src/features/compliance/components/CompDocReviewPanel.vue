<script setup lang="ts">
import { ref, watch } from 'vue'
import type { ICompDoc } from '@/features/compliance/models/compdocs'
import {
  createCompdocReview,
  decideCompdocReview,
  fetchCompdocReviews,
  type CompdocReview,
  type CompdocReviewRequest
} from '@/features/compliance/api/compdocLifecycle'
import { formatApiError } from '@/shared/api/apiError'
import {
  fetchCompdocOptions,
  type CompdocReferenceOption
} from '@/features/compliance/api/compdocOptions'

const props = defineProps<{
  show: boolean
  project: string
  document: ICompDoc
  canEdit: boolean
}>()
const emit = defineEmits<{ changed: [] }>()
const reviews = ref<CompdocReview[]>([])
const loading = ref(false)
const decisionNotes = ref<Record<string, string>>({})
const assignees = ref<CompdocReferenceOption[]>([])
const request = ref<CompdocReviewRequest>(emptyRequest())
let loadSequence = 0

watch(
  () => [props.show, props.document.id, props.project, props.document.version],
  ([show]) => {
    loadSequence += 1
    loading.value = false
    reviews.value = []
    assignees.value = []
    decisionNotes.value = {}
    request.value = emptyRequest()
    if (show) void load()
  },
  { immediate: true }
)

async function load() {
  if (!props.document.id) return
  const sequence = ++loadSequence
  const documentId = props.document.id
  const project = props.project
  loading.value = true
  try {
    const loadedReviews = await fetchCompdocReviews(project, documentId)
    if (sequence !== loadSequence) return
    reviews.value = loadedReviews
    if (props.canEdit) {
      const loadedAssignees = await fetchCompdocOptions(project, 'user')
      if (sequence !== loadSequence) return
      assignees.value = loadedAssignees
    }
  } catch (error) {
    if (sequence === loadSequence) window.$message.error(formatApiError(error))
  } finally {
    if (sequence === loadSequence) loading.value = false
  }
}

function emptyRequest(): CompdocReviewRequest {
  return {
    version: props.document.version || 0,
    kind: 'review',
    assignee: null,
    due_date: null,
    request_note: ''
  }
}

async function createReview() {
  if (
    !props.document.id ||
    !request.value.version ||
    !request.value.assignee ||
    request.value.request_note.trim().length < 3
  ) {
    window.$message.warning('Select an assignee and enter a request note.')
    return
  }
  const sequence = loadSequence
  const documentId = props.document.id
  const project = props.project
  loading.value = true
  try {
    const created = await createCompdocReview(project, documentId, request.value)
    if (sequence !== loadSequence) return
    reviews.value = [created, ...reviews.value]
    request.value = emptyRequest()
    window.$message.success('Review task created.')
  } catch (error) {
    if (sequence === loadSequence) window.$message.error(formatApiError(error))
  } finally {
    if (sequence === loadSequence) loading.value = false
  }
}

async function decide(task: CompdocReview, status: 'approved' | 'changes_requested' | 'cancelled') {
  if (!props.document.id || (decisionNotes.value[task.id] || '').trim().length < 3) {
    window.$message.warning('Enter a decision note.')
    return
  }
  const sequence = loadSequence
  const documentId = props.document.id
  const project = props.project
  loading.value = true
  try {
    await decideCompdocReview(project, documentId, task.id, status, decisionNotes.value[task.id])
    if (sequence !== loadSequence) return
    await load()
    emit('changed')
  } catch (error) {
    if (sequence === loadSequence) window.$message.error(formatApiError(error))
  } finally {
    if (sequence === loadSequence) loading.value = false
  }
}
</script>

<template>
  <section class="workspace-section">
    <n-card v-if="canEdit" title="New review task" size="small">
      <n-grid responsive="screen" cols="1 s:2" :x-gap="12">
        <n-form-item-gi label="Task type">
          <n-select
            v-model:value="request.kind"
            :options="[
              { label: 'Review', value: 'review' },
              { label: 'Approval', value: 'approval' }
            ]"
          />
        </n-form-item-gi>
        <n-form-item-gi label="Assignee">
          <n-select
            v-model:value="request.assignee"
            :options="assignees.map((item) => ({ label: item.label, value: item.id }))"
            placeholder="Select a project user"
            filterable
          />
        </n-form-item-gi>
        <n-form-item-gi label="Due date">
          <n-date-picker v-model:formatted-value="request.due_date" type="date" clearable />
        </n-form-item-gi>
        <n-form-item-gi label="Request note">
          <n-input v-model:value="request.request_note" maxlength="500" show-count />
        </n-form-item-gi>
      </n-grid>
      <n-button
        type="primary"
        size="small"
        :disabled="!request.assignee || request.request_note.trim().length < 3"
        @click="createReview"
      >
        Create task
      </n-button>
    </n-card>
    <n-spin :show="loading">
      <n-card v-for="task in reviews" :key="task.id" size="small">
        <n-flex justify="space-between">
          <n-text>{{ task.kind }} · {{ task.assignee_username }}</n-text>
          <n-tag size="small">{{ task.status }}</n-tag>
        </n-flex>
        <n-text depth="3">{{ task.request_note }}</n-text>
        <n-space
          v-if="
            task.allowed_actions.approve ||
            task.allowed_actions.request_changes ||
            task.allowed_actions.cancel
          "
          vertical
        >
          <n-input
            v-model:value="decisionNotes[task.id]"
            maxlength="500"
            placeholder="Decision note"
          />
          <n-flex>
            <n-button
              v-if="task.allowed_actions.approve"
              size="small"
              type="success"
              @click="decide(task, 'approved')"
            >
              Approve
            </n-button>
            <n-button
              v-if="task.allowed_actions.request_changes"
              size="small"
              type="warning"
              @click="decide(task, 'changes_requested')"
            >
              Request changes
            </n-button>
            <n-button
              v-if="task.allowed_actions.cancel"
              size="small"
              quaternary
              type="error"
              @click="decide(task, 'cancelled')"
            >
              Cancel task
            </n-button>
          </n-flex>
        </n-space>
      </n-card>
      <n-empty v-if="!loading && !reviews.length" description="No review tasks." size="small" />
    </n-spin>
  </section>
</template>
