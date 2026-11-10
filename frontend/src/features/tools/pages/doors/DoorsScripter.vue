<template>
  <n-flex class="app-page-container">
    <n-card title="DOORS Script Generator (Excel)">
      <template #header-extra>
        <n-tooltip trigger="hover" :delay="500">
          <template #trigger>
            <n-button disabled> DXL Library </n-button>
          </template>
          Authenticated DXL library delivery is not available in this deployment.
        </n-tooltip>
      </template>
      <n-grid responsive="self" item-responsive cols="12" x-gap="12" y-gap="18">
        <n-grid-item span="12">
          <n-form-item label="Mode">
            <n-select v-model:value="mode" :options="modeOptions" aria-label="Script mode" />
          </n-form-item>
          <n-p depth="3">
            {{
              mode === 'update'
                ? 'Update all objects matching every selected Unique Attribute. Unique Attributes are not changed.'
                : 'Add objects at the end of the module. Existing combinations of Unique Attributes are skipped with a DXL warning.'
            }}
            Rows with an empty Unique Attribute are skipped. Review and save changes in DOORS
            manually.
          </n-p>
          <n-p depth="3">
            Matching is case-sensitive. Object Number and Absolute Number are read-only search
            fields for update mode. Date attributes accept Excel dates, dd.MM.yyyy, or yyyy-MM-dd;
            dates are validated before any changes are made. Contains searches use ISO date text.
          </n-p>
        </n-grid-item>
        <n-grid-item span="12">
          <n-form-item label="DOORS Module Path (optional attribute discovery)">
            <n-flex align="center" style="width: 100%" :wrap="true">
              <n-input
                v-model:value="modulePath"
                :disabled="attributesLoaded || attributesLoading"
                :input-props="{ 'aria-label': 'DOORS module path' }"
                placeholder="/Project/Module"
                style="flex: 1; min-width: min(220px, 100%)"
              />
              <n-button
                :loading="attributesLoading"
                :disabled="
                  attributesLoading || generating || (!attributesLoaded && !modulePath.trim())
                "
                @click="toggleAttributes"
              >
                {{ attributesLoaded ? 'Unload Attributes' : 'Load Attributes' }}
              </n-button>
            </n-flex>
          </n-form-item>
          <n-alert v-if="attributeError" type="error" :bordered="false">{{
            attributeError
          }}</n-alert>
          <PageJobStatus
            :job="attributeJob"
            :cancelling="attributeCancelling"
            :downloading="attributeDownloading"
            @cancel="cancelAttributes"
            @download="downloadAttributes"
            @open="openAttributeJob"
          />
        </n-grid-item>
        <n-grid-item span="12">
          <n-upload
            :max="1"
            accept=".xlsm,.xlsx"
            :custom-request="handleUploadReq"
            @change="handleFileChange"
            @remove="handleFileRemove"
          >
            <n-upload-dragger>
              <n-text style="font-size: 16px"> Click or drag a file to this area to upload </n-text>
              <n-p depth="3" style="margin: 8px 0 0 0">
                Upload the excel file you wish to synchronize with DOORS.
              </n-p>
            </n-upload-dragger>
          </n-upload>
        </n-grid-item>

        <n-grid-item span="0:12 700:3" v-if="fileList.length != 0">
          <n-h4 style="margin-bottom: -10px"> Excel Column Names </n-h4>
        </n-grid-item>
        <n-grid-item span="0:12 700:4" v-if="fileList.length != 0">
          <n-h4 style="margin-bottom: -10px"> DOORS Column Names </n-h4>
        </n-grid-item>
        <n-grid-item span="0:12 700:2" v-if="fileList.length != 0">
          <n-h4 style="margin-bottom: -10px"> Unique Attribute </n-h4>
        </n-grid-item>
        <n-grid-item span="0:12 700:3" v-if="fileList.length != 0">
          <n-h4 style="margin-bottom: -10px"> Match Mode </n-h4>
        </n-grid-item>

        <n-grid-item span="12" v-for="(column, index) in columns" :key="index">
          <n-grid responsive="self" item-responsive cols="12" x-gap="12" y-gap="18">
            <n-grid-item span="0:12 700:3">
              <n-input
                v-model:value="column.excel"
                :input-props="{ 'aria-label': `Excel column ${column.excel}` }"
                readonly
              />
            </n-grid-item>
            <n-grid-item span="0:12 700:4">
              <n-input
                v-if="!attributesLoaded"
                v-model:value="column.doors"
                :input-props="{ 'aria-label': `DOORS attribute for ${column.excel}` }"
              />
              <n-select
                v-else
                v-model:value="column.doors"
                :options="attributeOptions"
                filterable
                clearable
                :input-props="{ 'aria-label': `DOORS attribute for ${column.excel}` }"
                :aria-label="`DOORS attribute for ${column.excel}`"
              />
            </n-grid-item>
            <n-grid-item span="0:12 700:2">
              <n-switch
                v-model:value="column.search"
                :aria-label="`Unique Attribute for ${column.excel}`"
              />
            </n-grid-item>
            <n-grid-item span="0:12 700:3">
              <n-select
                v-if="column.search"
                v-model:value="column.match_mode"
                :options="matchModeOptions"
                :input-props="{ 'aria-label': `Match mode for ${column.excel}` }"
                :aria-label="`Match mode for ${column.excel}`"
              />
            </n-grid-item>
          </n-grid>
        </n-grid-item>
        <n-grid-item span="12" v-if="fileList.length != 0">
          <n-flex justify="center">
            <n-button
              type="success"
              ghost
              :loading="generating"
              :disabled="generating || attributesLoading"
              @click="createScript"
              >Generate</n-button
            >
          </n-flex>
        </n-grid-item>
      </n-grid>
    </n-card>
  </n-flex>

  <n-modal
    v-model:show="modal.show"
    preset="card"
    title="Script"
    transform-origin="center"
    class="app-modal app-modal--large"
  >
    <template #header-extra>
      {{ modal.rowCount }} rows · {{ modal.mappingCount }} mappings
    </template>
    <n-scrollbar style="max-height: 500px; white-space: pre-wrap">
      {{ modal.content }}
    </n-scrollbar>
    <template #action>
      <n-flex justify="center">
        <n-button type="info" @click="copyToClipboard">Copy</n-button>
      </n-flex>
    </template>
  </n-modal>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import {
  createDoorsScript,
  getExcelColumns,
  type DoorsScriptMode,
  type DoorsScriptMatchMode
} from '@/features/tools/api/doorsScript'
import type { UploadCustomRequestOptions, UploadFileInfo } from 'naive-ui'
import { selectedUploadFile } from '@/shared/utils/uploads'
import { formatApiError } from '@/shared/api/apiError'
import PageJobStatus from '@/features/jobs/components/PageJobStatus.vue'
import { useDoorsScriptAttributes } from '@/features/tools/composables/useDoorsScriptAttributes'

type OptionItem = {
  excel: string
  doors: string | null
  search: boolean
  match_mode: DoorsScriptMatchMode
}

const columns = ref<OptionItem[]>([])
const fileList = ref<UploadFileInfo[]>([])
const mode = ref<DoorsScriptMode>('update')
const generating = ref(false)
const {
  modulePath,
  names: attributeNames,
  options: attributeOptions,
  loaded: attributesLoaded,
  loading: attributesLoading,
  error: attributeError,
  load: loadAttributes,
  unload: unloadAttributes,
  monitor: {
    job: attributeJob,
    cancelling: attributeCancelling,
    downloading: attributeDownloading,
    cancel: cancelAttributes,
    download: downloadAttributes,
    openJobCenter: openAttributeJob
  }
} = useDoorsScriptAttributes()

watch(attributeNames, (names) => {
  if (!names.length) return
  const validNames = new Set(names)
  const cleared: string[] = []
  for (const column of columns.value) {
    const name = column.doors?.trim() || ''
    if (name && !validNames.has(name)) {
      column.doors = ''
      cleared.push(column.excel)
    } else column.doors = name
  }
  if (cleared.length)
    window.$message.warning(
      `Select a module attribute again for Excel columns: ${cleared.join(', ')}.`
    )
})

function toggleAttributes() {
  if (attributesLoaded.value) unloadAttributes()
  else void loadAttributes()
}
const modeOptions = [
  { label: 'Update Existing Objects', value: 'update' },
  { label: 'Create New Objects', value: 'create' }
]
const matchModeOptions = [
  { label: 'Exact match', value: 'exact' },
  { label: 'Contains', value: 'contains' }
]

const modal = ref({
  show: false,
  content: '',
  rowCount: 0,
  mappingCount: 0
})

function handleFileChange(options: { fileList: UploadFileInfo[] }) {
  fileList.value = options.fileList
}

function handleFileRemove() {
  columns.value = []
}

function createScript() {
  if (generating.value || attributesLoading.value) return
  const selectedFile = selectedUploadFile(fileList.value)
  if (!selectedFile) return
  const uniqueColumns = columns.value.filter((item) => item.search)
  if (!uniqueColumns.length) {
    window.$message.error('Select at least one Unique Attribute.')
    return
  }
  if (uniqueColumns.some((item) => !item.doors?.trim())) {
    window.$message.error('Enter a DOORS attribute name for every selected Unique Attribute.')
    return
  }
  const filtered = columns.value
    .filter((item) => item.doors?.trim())
    .map((item) => ({ ...item, doors: item.doors!.trim() }))
  if (
    filtered.some(
      (item) =>
        ['object number', 'absolute number'].includes(item.doors.toLowerCase()) &&
        (mode.value === 'create' || !item.search)
    )
  ) {
    window.$message.error(
      'Object Number and Absolute Number are read-only; use them only as Unique Attributes in update mode.'
    )
    return
  }
  const formData = new FormData()
  formData.append('file', selectedFile)
  formData.append('json', JSON.stringify(filtered))
  formData.append('mode', mode.value)
  generating.value = true
  createDoorsScript(formData)
    .then((result) => {
      modal.value.content = result.script
      modal.value.rowCount = result.row_count
      modal.value.mappingCount = result.mapping_count
      modal.value.show = true
      window.$message.success('Script created successfully.')
    })
    .catch((error: unknown) => window.$message.error(formatApiError(error)))
    .finally(() => {
      generating.value = false
    })
}

function handleUploadReq({ file, onError }: UploadCustomRequestOptions) {
  const selectedFile = selectedUploadFile([file])
  if (!selectedFile) return onError()
  window.$loadingBar.start()
  const formData = new FormData()
  formData.append('file', selectedFile)
  getExcelColumns(formData)
    .then((res: string[]) => {
      const excelColumns = res
      if (excelColumns) {
        columns.value = excelColumns.map((excel) => ({
          excel,
          doors: '',
          search: false,
          match_mode: 'exact'
        }))
      }
      window.$message.success('Excel content successfully read.')
    })
    .catch(() => window.$message.error('The workbook columns could not be read.'))
    .finally(() => {
      window.$loadingBar.finish()
    })
}

async function copyToClipboard() {
  try {
    await navigator.clipboard.writeText(modal.value.content)
    window.$message.success('Script Copied')
  } catch (err) {
    console.error(err)
  }
}
</script>
