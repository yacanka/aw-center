<template>
  <n-card title="Compare">
    <n-space vertical size="large">
      <n-text depth="3"
        >Compare two versions of a Word, Excel or PDF file. Every content change stays visible, even
        when the match is strong.</n-text
      >
      <div class="comparison-uploads">
        <n-upload
          v-for="side in sides"
          :key="side"
          :max="1"
          :default-upload="false"
          :disabled="busy"
          accept=".docx,.docm,.xlsx,.xlsm,.pdf"
          @change="handleUpload(side, $event)"
        >
          <n-upload-dragger>
            <n-text strong>{{ side === 'first' ? 'Old file' : 'New file' }}</n-text>
            <n-p depth="3">Click or drag a Word, Excel or PDF file here</n-p>
          </n-upload-dragger>
        </n-upload>
      </div>
      <n-alert v-if="fileError" type="error" :bordered="false">{{ fileError }}</n-alert>
      <n-flex v-else-if="family" align="center">
        <n-tag type="info">{{
          family === 'excel' ? 'Excel table' : family === 'word' ? 'Word text' : 'PDF text'
        }}</n-tag>
        <n-text depth="3">{{
          family === 'excel'
            ? 'One selected table per file · formulas are not evaluated'
            : 'Text content only · no OCR, image or layout comparison'
        }}</n-text>
      </n-flex>
      <n-form label-placement="top" :disabled="busy">
        <div class="comparison-settings">
          <n-form-item label="Matching preset">
            <n-select :value="options.preset" :options="presetOptions" @update:value="setPreset" />
          </n-form-item>
          <n-form-item label="Report format">
            <n-select v-model:value="options.output_type" :options="outputOptions" />
          </n-form-item>
        </div>
        <n-text depth="3">{{ presetDescription }}</n-text>
        <div v-if="options.preset === 'custom'" class="comparison-settings custom-thresholds">
          <n-form-item label="Strong match threshold (equal ratio)">
            <n-input-number
              :value="options.equal_ratio"
              :min="0.01"
              :max="1"
              :step="0.01"
              @update:value="options.equal_ratio = $event ?? 0"
            />
          </n-form-item>
          <n-form-item label="Possible match threshold (weak equal ratio)">
            <n-input-number
              :value="options.weak_equal_ratio"
              :min="0.01"
              :max="1"
              :step="0.01"
              @update:value="options.weak_equal_ratio = $event ?? 0"
            />
          </n-form-item>
        </div>
        <n-alert v-if="!validOptions" type="error"
          >Use 0 &lt; possible threshold ≤ strong threshold ≤ 1.</n-alert
        >
        <n-p depth="3"
          >{{ options.equal_ratio }} strong / {{ options.weak_equal_ratio }} possible. These are
          starting points for matching; they never hide a real difference.</n-p
        >
      </n-form>
      <ExcelMatching
        v-if="inspection"
        :inspection="inspection"
        :selection="selection"
        :disabled="busy"
        @update="updateSelection"
      />
      <n-alert v-if="dirty" type="info" :bordered="false"
        >Matching settings changed. Inspect the tables again before comparing.</n-alert
      >
      <n-flex justify="end">
        <n-button
          v-if="family === 'excel'"
          :disabled="!canInspect"
          :loading="queueing || loadingInspection"
          @click="inspect"
        >
          {{ inspection ? 'Inspect again' : 'Inspect tables' }}
        </n-button>
        <n-button type="primary" :disabled="!canCompare" :loading="queueing" @click="compare"
          >Compare and download</n-button
        >
      </n-flex>
      <n-alert v-if="error || errorMessage" type="error" :bordered="false">
        {{ error || errorMessage }}
        <n-button
          v-if="job?.kind === 'comparison.inspect' && job.status === 'succeeded'"
          size="small"
          @click="retryInspection"
          >Reload inspection</n-button
        >
      </n-alert>
      <PageJobStatus
        :job="displayJob"
        :cancelling="cancelling"
        :downloading="downloading"
        download-label="Download report"
        @cancel="cancel"
        @download="download"
        @open="openJobCenter"
      />
    </n-space>
  </n-card>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { UploadFileInfo } from 'naive-ui'
import { selectedUploadFile } from '@/shared/utils/uploads'
import PageJobStatus from '@/features/jobs/components/PageJobStatus.vue'
import ExcelMatching from '@/features/tools/components/compare/ExcelMatching.vue'
import { useComparison } from '@/features/tools/composables/useComparison'
const sides = ['first', 'second'] as const
const {
  family,
  fileError,
  options,
  presets,
  inspection,
  selection,
  queueing,
  loadingInspection,
  error,
  dirty,
  busy,
  canInspect,
  canCompare,
  validOptions,
  setFile,
  setPreset,
  updateSelection,
  inspect,
  compare,
  retryInspection,
  job,
  cancelling,
  downloading,
  errorMessage,
  cancel,
  download,
  openJobCenter
} = useComparison()
const presetOptions = computed(() => [
  ...presets.value.map((item) => ({ label: item.label, value: item.id })),
  { label: 'Custom', value: 'custom' }
])
const presetDescription = computed(
  () =>
    presets.value.find((item) => item.id === options.value.preset)?.description ||
    'Choose the two matching thresholds below.'
)
const outputOptions = [
  { label: 'Word report (.docx) — marked changes for reading', value: 'word' },
  { label: 'Excel report (.xlsx) — filterable detail', value: 'excel' }
]
// Inspection artifacts power the guidance above; the visible download is the
// user's chosen report, not the internal inspection JSON.
const displayJob = computed(() =>
  job.value?.kind === 'comparison.inspect' ? { ...job.value, download_url: null } : job.value
)
function handleUpload(side: 'first' | 'second', value: { fileList: UploadFileInfo[] }) {
  setFile(side, selectedUploadFile(value.fileList, false))
}
</script>

<style scoped>
.comparison-uploads,
.comparison-settings {
  display: grid;
  gap: 18px;
  grid-template-columns: repeat(2, minmax(0, 1fr));
}
.comparison-uploads > *,
.comparison-settings > * {
  min-width: 0;
}
.custom-thresholds {
  margin-top: 16px;
}
@media (max-width: 700px) {
  .comparison-uploads,
  .comparison-settings {
    grid-template-columns: 1fr;
  }
}
</style>
