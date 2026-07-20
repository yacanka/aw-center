<template>
  <n-button ghost type="error" :disabled="count == 0" @click="open">
    <template #icon><Delete24Regular /></template>
    Delete All
  </n-button>
  <n-modal
    v-model:show="visible"
    preset="card"
    title="Delete all compliance documents"
    :style="{ width: '620px' }"
    :mask-closable="false"
  >
    <n-space vertical>
      <n-alert type="error" :bordered="false">
        This permanently deletes {{ count }} {{ project.toUpperCase() }} compliance document
        records. Historical deletion evidence is retained.
      </n-alert>
      <n-text>Type the exact phrase to continue:</n-text>
      <n-text code>{{ confirmationPhrase }}</n-text>
      <n-input v-model:value="confirmation" :placeholder="confirmationPhrase" />
    </n-space>
    <template #action>
      <n-button :disabled="busy" @click="visible = false">Cancel</n-button>
      <n-button type="error" :loading="busy" :disabled="!isConfirmed" @click="removeAll">
        Delete {{ count }} records
      </n-button>
    </template>
  </n-modal>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { Delete24Regular } from '@vicons/fluent'
import { useCompdocStore } from '@/stores/compdoc'

const props = defineProps<{ project: string; count: number }>()
const emit = defineEmits<{ deleted: [] }>()
const store = useCompdocStore()
const visible = ref(false)
const busy = ref(false)
const confirmation = ref('')
const confirmationPhrase = computed(
  () => `DELETE ${props.project.toUpperCase()} COMPLIANCE DOCUMENTS`
)
const isConfirmed = computed(
  () => confirmation.value === confirmationPhrase.value && props.count > 0 && !busy.value
)

function open(): void {
  confirmation.value = ''
  visible.value = true
}

async function removeAll(): Promise<void> {
  if (!isConfirmed.value) return
  busy.value = true
  try {
    await store.deleteCompdocs({ confirmation: confirmation.value, expected_count: props.count })
    visible.value = false
    emit('deleted')
  } finally {
    busy.value = false
  }
}
</script>
