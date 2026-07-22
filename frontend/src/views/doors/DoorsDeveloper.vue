<template>
  <n-space vertical size="large">
    <n-card title="Developer / DOORS Endpoint Tester">
      <n-alert type="warning" title="Developer-only diagnostics">
        Mutating endpoints require an administrator token. Use non-production modules when testing.
      </n-alert>
      <n-form label-placement="top" style="margin-top: 16px">
        <n-grid :cols="2" :x-gap="16">
          <n-form-item-gi label="Module Path">
            <n-input v-model:value="modulePath" placeholder="/Project/Folder/Module" />
          </n-form-item-gi>
          <n-form-item-gi label="Attributes (one per line)">
            <n-input v-model:value="attributesText" type="textarea" :autosize="{ minRows: 2 }" />
          </n-form-item-gi>
          <n-form-item-gi label="Absolute Number">
            <n-input-number v-model:value="absoluteNumber" :min="1" style="width: 100%" />
          </n-form-item-gi>
          <n-form-item-gi label="List Limit">
            <n-input-number v-model:value="limit" :min="1" :max="1000" style="width: 100%" />
          </n-form-item-gi>
          <n-form-item-gi label="Loop">
            <n-select v-model:value="loop" :options="loopOptions" />
          </n-form-item-gi>
          <n-form-item-gi label="Create Position">
            <n-select v-model:value="position" :options="positionOptions" />
          </n-form-item-gi>
          <n-form-item-gi label="Relative Absolute Number">
            <n-input-number v-model:value="relativeAbsoluteNumber" :min="1" style="width: 100%" />
          </n-form-item-gi>
          <n-form-item-gi label="Scalar Attributes JSON">
            <n-input v-model:value="attributesJson" type="textarea" :autosize="{ minRows: 4 }" />
          </n-form-item-gi>
        </n-grid>
      </n-form>
      <n-space>
        <n-button @click="runStatus">GET status</n-button>
        <n-button type="info" @click="runApplicationResultProbe">
          Test Application.Result
        </n-button>
        <n-button @click="runCheckModule">POST modules/check</n-button>
        <n-button @click="runListObjects">POST objects</n-button>
        <n-button @click="runGetObject">POST objects/detail</n-button>
        <n-button type="warning" @click="runUpdateObject">PATCH objects/update</n-button>
        <n-button type="error" @click="runCreateObject">POST objects/create</n-button>
      </n-space>
    </n-card>
    <n-card title="Last Response">
      <n-code :code="responseText" language="json" word-wrap />
    </n-card>
  </n-space>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import {
  checkDoorsModule,
  createDoorsObject,
  fetchDoorsObject,
  fetchDoorsObjects,
  fetchDoorsStatus,
  probeDoorsApplicationResult,
  updateDoorsObject,
  type DoorsLoop,
  type DoorsPosition
} from '@/services/engineeringIntegrations'
import { formatApiError } from '@/services/apiError'

const modulePath = ref('')
const attributesText = ref('Object Heading\nObject Text')
const absoluteNumber = ref(1)
const limit = ref(25)
const loop = ref<DoorsLoop>('entire')
const position = ref<DoorsPosition>('after')
const relativeAbsoluteNumber = ref(1)
const attributesJson = ref(
  '{\n  "Object Heading": "Developer test",\n  "Object Text": "DOORS API test"\n}'
)
const lastResponse = ref<unknown>({ detail: 'No request has been sent yet.' })

const loopOptions = ['module', 'entire', 'all', 'document'].map((value) => ({
  label: value,
  value
}))
const positionOptions = ['first', 'after', 'before', 'below', 'below_last'].map((value) => ({
  label: value,
  value
}))
const attributes = computed(() => attributesText.value.split('\n').map(trimValue).filter(Boolean))
const responseText = computed(() => JSON.stringify(lastResponse.value, null, 2))

/** Runs the non-secret DOORS status endpoint. */
async function runStatus() {
  await capture(() => fetchDoorsStatus())
}

/** Runs a fixed oleSetResult/Application.Result round-trip diagnostic. */
async function runApplicationResultProbe() {
  await capture(() => probeDoorsApplicationResult())
}

/** Runs the module accessibility endpoint with the current module path. */
async function runCheckModule() {
  await capture(() => checkDoorsModule(modulePath.value))
}

/** Runs the object list endpoint with current list fields. */
async function runListObjects() {
  await capture(() =>
    fetchDoorsObjects(modulePath.value, attributes.value, limit.value, loop.value)
  )
}

/** Runs the object detail endpoint with current object fields. */
async function runGetObject() {
  await capture(() => fetchDoorsObject(modulePath.value, absoluteNumber.value, attributes.value))
}

/** Runs the admin-only object update endpoint with scalar JSON attributes. */
async function runUpdateObject() {
  await capture(() =>
    updateDoorsObject(modulePath.value, absoluteNumber.value, parseScalarAttributes())
  )
}

/** Runs the admin-only object creation endpoint with scalar JSON attributes. */
async function runCreateObject() {
  const relative = position.value === 'first' ? undefined : relativeAbsoluteNumber.value
  await capture(() =>
    createDoorsObject(modulePath.value, position.value, relative, parseScalarAttributes())
  )
}

async function capture(action: () => Promise<unknown>) {
  try {
    lastResponse.value = await action()
  } catch (error) {
    lastResponse.value = { error: formatApiError(error) }
  }
}

function parseScalarAttributes() {
  return JSON.parse(attributesJson.value) as Record<string, string | number | boolean | null>
}

function trimValue(value: string) {
  return value.trim()
}
</script>
