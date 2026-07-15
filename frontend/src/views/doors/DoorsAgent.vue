<template>
  <n-space vertical size="large">
    <n-card title="IBM Rational DOORS Agent">
      <n-alert :type="readinessType" :bordered="false">
        {{ readinessMessage }}
      </n-alert>
      <n-form label-placement="top" style="margin-top: 16px">
        <n-form-item label="Module path">
          <n-input v-model:value="modulePath" placeholder="/Project/System Requirements" />
        </n-form-item>
        <n-grid :cols="2" :x-gap="16" responsive="screen">
          <n-form-item-gi label="Attributes (comma separated)">
            <n-input v-model:value="attributeText" />
          </n-form-item-gi>
          <n-form-item-gi label="Maximum objects">
            <n-input-number v-model:value="limit" :min="1" :max="1000" />
          </n-form-item-gi>
        </n-grid>
        <n-space>
          <n-button :loading="isChecking" :disabled="!canRun" @click="verifyModule">
            Check module
          </n-button>
          <n-button
            type="primary"
            :loading="isLoadingObjects"
            :disabled="!canRun"
            @click="loadObjects"
          >
            List objects
          </n-button>
        </n-space>
      </n-form>
    </n-card>

    <n-card v-if="objects.length" :title="`Objects (${objects.length})`">
      <n-data-table :columns="columns" :data="objects" :pagination="{ pageSize: 25 }" />
    </n-card>
  </n-space>
</template>

<script setup lang="ts">
import { computed, h, onMounted, ref } from 'vue'
import type { DataTableColumns } from 'naive-ui'
import { NCode } from 'naive-ui'
import { formatApiError } from '@/services/apiError'
import {
  checkDoorsModule,
  fetchDoorsObjects,
  fetchDoorsStatus,
  type DoorsObject,
  type DoorsStatus
} from '@/services/engineeringIntegrations'

const modulePath = ref('')
const attributeText = ref('Object Heading, Object Text')
const limit = ref(250)
const status = ref<DoorsStatus | null>(null)
const objects = ref<DoorsObject[]>([])
const isChecking = ref(false)
const isLoadingObjects = ref(false)

const attributes = computed(() =>
  attributeText.value
    .split(',')
    .map((value) => value.trim())
    .filter(Boolean)
    .slice(0, 50)
)
const canRun = computed(
  () => Boolean(modulePath.value.trim()) && Boolean(status.value?.platform_supported)
)
const readinessType = computed(() =>
  status.value?.configured && status.value.platform_supported ? 'success' : 'warning'
)
const readinessMessage = computed(() => {
  if (!status.value?.platform_supported) return 'DOORS OLE automation requires a Windows backend.'
  if (!status.value.configured) return 'The DOORS executable is not configured.'
  return 'Use an authenticated DOORS desktop session to run read operations.'
})
const columns: DataTableColumns<DoorsObject> = [
  { title: 'Absolute Number', key: 'absolute_number', width: 150 },
  { title: 'Identifier', key: 'identifier', width: 220 },
  { title: 'Level', key: 'level', width: 90 },
  {
    title: 'Attributes',
    key: 'attributes',
    render: (row) => h(NCode, { code: JSON.stringify(row.attributes, null, 2), wordWrap: true })
  }
]

onMounted(loadStatus)

async function loadStatus() {
  try {
    status.value = await fetchDoorsStatus()
  } catch (error) {
    window.$message.error(formatApiError(error))
  }
}

async function verifyModule() {
  isChecking.value = true
  try {
    await checkDoorsModule(modulePath.value.trim())
    window.$message.success('DOORS module is accessible.')
  } catch (error) {
    window.$message.error(formatApiError(error))
  } finally {
    isChecking.value = false
  }
}

async function loadObjects() {
  isLoadingObjects.value = true
  try {
    const response = await fetchDoorsObjects(modulePath.value.trim(), attributes.value, limit.value)
    objects.value = response.results
  } catch (error) {
    window.$message.error(formatApiError(error))
  } finally {
    isLoadingObjects.value = false
  }
}
</script>
