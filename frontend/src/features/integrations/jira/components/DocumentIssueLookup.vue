<script setup lang="ts">
import { ref, onBeforeUnmount } from 'vue'
import {
  resolveDocumentIssue,
  documentError,
  type ResolvedDocumentIssue
} from '../api/documentTemplates'

const props = defineProps<{ label: string; disabled?: boolean }>()
const emit = defineEmits<{ resolved: [value: ResolvedDocumentIssue | null] }>()
const input = ref('')
const loading = ref(false)
const error = ref('')
let request: AbortController | undefined

function change(value: string) {
  request?.abort()
  loading.value = false
  input.value = value
  error.value = ''
  emit('resolved', null)
}

async function resolve() {
  if (!input.value.trim() || props.disabled || loading.value) return
  request?.abort()
  const current = new AbortController()
  request = current
  error.value = ''
  loading.value = true
  emit('resolved', null)
  try {
    const issue = await resolveDocumentIssue(input.value.trim(), current.signal)
    if (!current.signal.aborted) emit('resolved', issue)
  } catch (failure) {
    if (!current.signal.aborted) error.value = documentError(failure)
  } finally {
    if (!current.signal.aborted) loading.value = false
  }
}

onBeforeUnmount(() => {
  request?.abort()
  emit('resolved', null)
})
</script>

<template>
  <form @submit.prevent="resolve">
    <n-form-item
      :label="label"
      :show-feedback="false"
      :label-props="{ for: 'jira-document-issue' }"
    >
      <n-input
        :value="input"
        :maxlength="2048"
        :input-props="{ id: 'jira-document-issue' }"
        :disabled="disabled"
        placeholder="Issue key or JIRA browse URL"
        @update:value="change"
      />
    </n-form-item>
    <n-flex class="lookup-action">
      <n-button
        attr-type="submit"
        :disabled="disabled || !input.trim() || loading"
        :loading="loading"
        >Look up issue</n-button
      >
    </n-flex>
    <n-alert v-if="error" type="error">{{ error }}</n-alert>
  </form>
</template>

<style scoped>
.lookup-action {
  margin-block: 8px;
}
</style>
