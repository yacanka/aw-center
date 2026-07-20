<template>
  <n-form label-placement="top">
    <n-form-item label="Automation recipe">
      <n-select
        v-model:value="recipeId"
        :options="recipeOptions"
        :loading="loading"
        placeholder="Select workflow"
      />
    </n-form-item>
    <n-p v-if="selectedRecipe" depth="3">{{ selectedRecipe.description }}</n-p>
    <n-space v-if="selectedRecipe" style="margin-bottom: 16px">
      <n-tag v-for="step in selectedRecipe.steps" :key="step.sequence" round>
        {{ step.sequence }}. {{ step.label }}
      </n-tag>
    </n-space>
    <n-upload
      ref="uploadForm"
      :max="1"
      :default-upload="false"
      :accept="acceptedExtensions"
      @change="handleFileChange"
    >
      <n-upload-dragger>
        <n-text>Click or drag a {{ selectedRecipe?.input.label || 'source file' }}</n-text>
        <n-p depth="3">{{ selectedRecipe?.input.help || 'Select a recipe first.' }}</n-p>
      </n-upload-dragger>
    </n-upload>
    <n-form-item
      v-for="field in selectedRecipe?.parameters || []"
      :key="field.name"
      :label="field.label"
      style="margin-top: 16px"
    >
      <n-select
        v-model:value="parameterValues[field.name]"
        :options="field.options"
        :placeholder="`Select ${field.label.toLocaleLowerCase()}`"
      />
    </n-form-item>
    <n-button type="primary" :loading="queueing" :disabled="!canQueue" @click="queueWorkflow">
      Start connected workflow
    </n-button>
  </n-form>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { UploadFileInfo, UploadInst } from 'naive-ui'
import { formatApiError } from '@/services/apiError'
import { createWorkflowRun, type WorkflowRecipe, type WorkflowRun } from '@/services/workflows'
import { selectedUploadFile } from '@/utils/uploads'

const props = defineProps<{ recipes: WorkflowRecipe[]; loading: boolean }>()
const emit = defineEmits<{
  queued: [workflow: WorkflowRun]
  error: [message: string]
}>()
const files = ref<UploadFileInfo[]>([])
const uploadForm = ref<UploadInst | null>(null)
const recipeId = ref<string | null>(null)
const parameterValues = ref<Record<string, string | null>>({})
const queueing = ref(false)
const submissionKey = ref(crypto.randomUUID())
const selectedRecipe = computed(() => props.recipes.find((item) => item.id === recipeId.value))
const selectedFile = computed(() => selectedUploadFile(files.value, false))
const acceptedExtensions = computed(() => selectedRecipe.value?.input.accept.join(',') || '')
const recipeOptions = computed(() =>
  props.recipes.map(({ id: value, title: label }) => ({ value, label }))
)
const canQueue = computed(() => {
  const required = selectedRecipe.value?.parameters.filter((field) => field.required) || []
  return Boolean(selectedFile.value && required.every((field) => parameterValues.value[field.name]))
})

watch(
  () => props.recipes,
  (catalog) => {
    if (!catalog.some((item) => item.id === recipeId.value)) recipeId.value = catalog[0]?.id || null
  },
  { immediate: true }
)
watch(recipeId, resetRecipeInput)

function resetRecipeInput(): void {
  uploadForm.value?.clear()
  files.value = []
  parameterValues.value = {}
  submissionKey.value = crypto.randomUUID()
}

function handleFileChange(value: { fileList: UploadFileInfo[] }): void {
  files.value = value.fileList
  submissionKey.value = crypto.randomUUID()
}

async function queueWorkflow(): Promise<void> {
  if (!recipeId.value || !selectedFile.value || !canQueue.value) return
  queueing.value = true
  try {
    const workflow = await createWorkflowRun(
      recipeId.value,
      selectedFile.value,
      parameterValues.value,
      submissionKey.value
    )
    resetRecipeInput()
    emit('queued', workflow)
  } catch (error) {
    emit('error', formatApiError(error))
  } finally {
    queueing.value = false
  }
}
</script>
