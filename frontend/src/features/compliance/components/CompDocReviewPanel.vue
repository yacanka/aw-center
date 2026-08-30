<script setup lang="ts">
import { ref, watch } from 'vue'
import type { ICompDoc } from '@/features/compliance/models/compdocs'
import {
  decideCompdocReview,
  fetchCompdocReviews,
  type CompdocReview
} from '@/features/compliance/api/compdocLifecycle'
import { formatApiError } from '@/shared/api/apiError'

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
    <n-alert v-if="canEdit" type="info" :bordered="false">
      Creating a new review is unavailable until the project-scoped assignee picker is exposed.
    </n-alert>
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
