<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { ICompDoc } from '@/features/compliance/models/compdocs'
import {
  fetchCompdocWork,
  updateCompdocWork,
  type CompdocWork
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
const work = ref<CompdocWork | null>(null)
const reason = ref('')
const loading = ref(false)
const ownerOptions = ref<CompdocReferenceOption[]>([])
const groupOptions = ref<CompdocReferenceOption[]>([])
let loadSequence = 0
const displayedOwnerOptions = computed(() =>
  includeCurrentOption(ownerOptions.value, work.value?.owner, work.value?.owner_username, 'User')
)
const displayedGroupOptions = computed(() =>
  includeCurrentOption(
    groupOptions.value,
    work.value?.owner_group,
    work.value?.owner_group_name,
    'Team'
  )
)

watch(
  () => [props.show, props.document.id, props.project],
  ([show]) => {
    loadSequence += 1
    loading.value = false
    work.value = null
    ownerOptions.value = []
    groupOptions.value = []
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
    const loadedWork = await fetchCompdocWork(project, documentId)
    if (sequence !== loadSequence) return
    work.value = loadedWork
    if (props.canEdit) {
      const [users, groups] = await Promise.all([
        fetchCompdocOptions(project, 'user'),
        fetchCompdocOptions(project, 'group')
      ])
      if (sequence !== loadSequence) return
      ownerOptions.value = users
      groupOptions.value = groups
    }
  } catch (error) {
    if (sequence === loadSequence) window.$message.error(formatApiError(error))
  } finally {
    if (sequence === loadSequence) loading.value = false
  }
}

async function save() {
  if (!props.document.id || !work.value) return
  const sequence = loadSequence
  const documentId = props.document.id
  const project = props.project
  loading.value = true
  try {
    const updated = await updateCompdocWork(project, documentId, {
      version: work.value.version,
      owner: work.value.owner,
      owner_group: work.value.owner_group,
      next_action_due_date: work.value.next_action_due_date,
      reason: reason.value
    })
    if (sequence !== loadSequence) return
    work.value = updated
    reason.value = ''
    window.$message.success('Document ownership updated.')
    emit('changed')
  } catch (error) {
    if (sequence === loadSequence) window.$message.error(formatApiError(error))
  } finally {
    if (sequence === loadSequence) loading.value = false
  }
}

function includeCurrentOption(
  options: CompdocReferenceOption[],
  currentId: number | null | undefined,
  currentLabel: string | undefined,
  fallbackType: string
) {
  const normalized = options.map((option) => ({ label: option.label, value: option.id }))
  if (
    currentId === null ||
    currentId === undefined ||
    normalized.some(({ value }) => value === currentId)
  ) {
    return normalized
  }
  return [
    { label: currentLabel || `${fallbackType} ${currentId}`, value: currentId },
    ...normalized
  ]
}
</script>

<template>
  <section class="workspace-section">
    <n-spin :show="loading">
      <n-grid v-if="work" responsive="screen" cols="1 s:2" :x-gap="12">
        <n-form-item-gi label="AW Center owner">
          <n-select
            v-model:value="work.owner"
            :options="displayedOwnerOptions"
            :disabled="!canEdit"
            placeholder="Unassigned"
            filterable
            clearable
          />
        </n-form-item-gi>
        <n-form-item-gi label="Owner team">
          <n-select
            v-model:value="work.owner_group"
            :options="displayedGroupOptions"
            :disabled="!canEdit"
            placeholder="Unassigned"
            filterable
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
        <n-form-item-gi v-if="canEdit" label="Change reason (optional)">
          <n-input
            v-model:value="reason"
            maxlength="255"
            show-count
            placeholder="Optional ownership explanation"
          />
        </n-form-item-gi>
      </n-grid>
      <n-button v-if="canEdit && work" size="small" type="primary" :loading="loading" @click="save">
        Save ownership
      </n-button>
    </n-spin>
    <n-text depth="3">Legacy/external responsible: {{ document.responsible || 'None' }}</n-text>
  </section>
</template>
