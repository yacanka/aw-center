<template>
  <n-form label-placement="top">
    <n-upload ref="uploadForm" :max="1" :default-upload="false" @change="handleFileChange">
      <n-upload-dragger>
        <n-text>Click or drag a source file for automation discovery</n-text>
        <n-p depth="3"
          >AW Center suggests a recipe when the file matches an automation trigger.</n-p
        >
      </n-upload-dragger>
    </n-upload>

    <n-alert v-if="triggerMessage" type="success" :bordered="false" style="margin-top: 16px">
      {{ triggerMessage }}
    </n-alert>
    <n-alert v-else-if="selectedFile" type="info" :bordered="false" style="margin-top: 16px">
      No automation trigger was detected. Select one of the available recipes manually.
    </n-alert>

    <n-form-item label="Automation recipe" style="margin-top: 16px">
      <n-select
        v-model:value="recipeId"
        :options="recipeOptions"
        :loading="loading"
        :disabled="!selectedFile"
        placeholder="Upload a file to discover or select a workflow"
      />
    </n-form-item>
    <n-p v-if="selectedRecipe" depth="3">{{ selectedRecipe.description }}</n-p>
    <n-space v-if="selectedRecipe" style="margin-bottom: 16px">
      <n-tag v-for="step in selectedRecipe.steps" :key="step.sequence" round>
        {{ step.sequence }}. {{ step.label }}
      </n-tag>
    </n-space>
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
const emit = defineEmits<{ queued: [workflow: WorkflowRun]; error: [message: string] }>()
const files = ref<UploadFileInfo[]>([])
const uploadForm = ref<UploadInst | null>(null)
const recipeId = ref<string | null>(null)
const parameterValues = ref<Record<string, string | null>>({})
const queueing = ref(false)
const submissionKey = ref(crypto.randomUUID())
const selectedRecipe = computed(() => props.recipes.find((item) => item.id === recipeId.value))
const selectedFile = computed(() => selectedUploadFile(files.value, false))
const recipeOptions = computed(() =>
  availableRecipes.value.map(({ id: value, title: label }) => ({ value, label }))
)
const matchingRecipes = computed(() => matchRecipesByFile(selectedFile.value, props.recipes))
const availableRecipes = computed(() =>
  matchingRecipes.value.length ? matchingRecipes.value : props.recipes
)
const triggerMessage = computed(() => {
  if (!selectedFile.value || matchingRecipes.value.length !== 1) return ''
  return `${matchingRecipes.value[0].title} was suggested from the uploaded file.`
})
const canQueue = computed(() => {
  const required = selectedRecipe.value?.parameters.filter((field) => field.required) || []
  return Boolean(
    selectedFile.value &&
    selectedRecipe.value &&
    required.every((field) => parameterValues.value[field.name])
  )
})

watch(() => props.recipes, selectSuggestedRecipe, { immediate: true })
watch(matchingRecipes, selectSuggestedRecipe)

function selectSuggestedRecipe(): void {
  const recipes = availableRecipes.value
  if (!recipes.some((item) => item.id === recipeId.value)) recipeId.value = recipes[0]?.id || null
}

function resetRecipeInput(): void {
  uploadForm.value?.clear()
  files.value = []
  recipeId.value = props.recipes[0]?.id || null
  parameterValues.value = {}
  submissionKey.value = crypto.randomUUID()
}

function handleFileChange(value: { fileList: UploadFileInfo[] }): void {
  files.value = value.fileList
  parameterValues.value = {}
  submissionKey.value = crypto.randomUUID()
  selectSuggestedRecipe()
}

function matchRecipesByFile(file: File | null, recipes: WorkflowRecipe[]): WorkflowRecipe[] {
  if (!file) return []
  const fileName = file.name.toLocaleLowerCase()
  return recipes.filter((recipe) =>
    recipe.input.accept.some((extension) => fileName.endsWith(extension.toLocaleLowerCase()))
  )
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
