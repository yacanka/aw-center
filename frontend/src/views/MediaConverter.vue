<template>
  <n-space vertical size="large">
    <n-card title="Media Converter">
      <n-alert type="info" :bordered="false">
        Import image, audio, or video files, resize frames, change target size settings, and convert
        extensions through the server-side FFmpeg executable.
      </n-alert>
      <n-form label-placement="top" style="margin-top: 16px">
        <n-form-item label="Input file">
          <MediaUploadDropzone @selected="setFile" />
        </n-form-item>
        <n-grid :cols="4" :x-gap="16" responsive="screen">
          <n-form-item-gi label="Output extension">
            <n-select v-model:value="parameters.output_extension" :options="extensionOptions" />
          </n-form-item-gi>
          <n-form-item-gi label="Width (px)">
            <n-input-number v-model:value="parameters.width" clearable :min="16" :max="7680" />
          </n-form-item-gi>
          <n-form-item-gi label="Height (px)">
            <n-input-number v-model:value="parameters.height" clearable :min="16" :max="4320" />
          </n-form-item-gi>
          <n-form-item-gi label="Video bitrate preset">
            <n-select v-model:value="videoBitratePreset" :options="videoBitrateOptions" />
          </n-form-item-gi>
          <n-form-item-gi
            v-if="videoBitratePreset === customPreset"
            label="Custom video bitrate (kbps)"
          >
            <n-input-number v-model:value="parameters.video_bitrate_kbps" clearable :min="1" />
          </n-form-item-gi>
          <n-form-item-gi label="Audio bitrate preset">
            <n-select v-model:value="audioBitratePreset" :options="audioBitrateOptions" />
          </n-form-item-gi>
          <n-form-item-gi
            v-if="audioBitratePreset === customPreset"
            label="Custom audio bitrate (kbps)"
          >
            <n-input-number v-model:value="parameters.audio_bitrate_kbps" clearable :min="1" />
          </n-form-item-gi>
        </n-grid>
        <n-space>
          <n-button
            type="primary"
            :loading="isPreviewing"
            :disabled="!selectedFile"
            @click="previewSize"
          >
            Preview output size
          </n-button>
          <n-button
            type="success"
            :loading="isConverting"
            :disabled="!selectedFile"
            @click="convertFile"
          >
            Convert and download
          </n-button>
        </n-space>
      </n-form>
    </n-card>
    <n-card v-if="preview" title="Output preview">
      <n-descriptions :column="3" bordered>
        <n-descriptions-item label="Estimated size">
          {{ formatBytes(preview.estimated_bytes) }}
        </n-descriptions-item>
        <n-descriptions-item label="Duration">
          {{ formatDuration(preview.duration_seconds) }}
        </n-descriptions-item>
        <n-descriptions-item label="Method">{{ preview.method }}</n-descriptions-item>
      </n-descriptions>
    </n-card>
  </n-space>
</template>

<script setup lang="ts">
import { reactive, ref, watch } from 'vue'
import MediaUploadDropzone from '@/components/MediaUploadDropzone.vue'
import { formatApiError } from '@/services/apiError'
import {
  convertMedia,
  previewMediaConversion,
  type MediaPreviewResult
} from '@/services/mediaTools'

const customPreset = 'custom'
const extensionValues = [
  'mp4',
  'webm',
  'mov',
  'mkv',
  'avi',
  'mp3',
  'wav',
  'jpg',
  'png',
  'webp',
  'gif'
]
const extensionOptions = extensionValues.map((value) => ({ label: value.toUpperCase(), value }))
const videoBitrateOptions = createBitrateOptions([750, 1500, 3000, 6000, 12000])
const audioBitrateOptions = createBitrateOptions([96, 128, 192, 256, 320])

const selectedFile = ref<File | null>(null)
const preview = ref<MediaPreviewResult | null>(null)
const isPreviewing = ref(false)
const isConverting = ref(false)
const videoBitratePreset = ref<number | string>(1500)
const audioBitratePreset = ref<number | string>(128)
const parameters = reactive({
  output_extension: 'mp4',
  width: null as number | null,
  height: null as number | null,
  video_bitrate_kbps: 1500 as number | null,
  audio_bitrate_kbps: 128 as number | null
})

watch(videoBitratePreset, (value) => applyPreset(value, 'video_bitrate_kbps'))
watch(audioBitratePreset, (value) => applyPreset(value, 'audio_bitrate_kbps'))

function setFile(file: File | null) {
  selectedFile.value = file
  preview.value = null
}

async function previewSize() {
  if (!selectedFile.value) return
  isPreviewing.value = true
  try {
    preview.value = await previewMediaConversion(selectedFile.value, parameters)
  } catch (error) {
    window.$message.error(formatApiError(error))
  } finally {
    isPreviewing.value = false
  }
}

async function convertFile() {
  if (!selectedFile.value) return
  isConverting.value = true
  try {
    const blob = await convertMedia(selectedFile.value, parameters)
    downloadBlob(blob, `converted.${parameters.output_extension}`)
  } catch (error) {
    window.$message.error(formatApiError(error))
  } finally {
    isConverting.value = false
  }
}

function createBitrateOptions(values: number[]) {
  return [
    ...values.map((value) => ({ label: `${value} kbps`, value })),
    { label: 'Other', value: customPreset }
  ]
}

function applyPreset(value: number | string, field: 'video_bitrate_kbps' | 'audio_bitrate_kbps') {
  if (value === customPreset) return

  parameters[field] = Number(value)
}

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  URL.revokeObjectURL(url)
}

function formatBytes(bytes: number) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

function formatDuration(seconds: number | null) {
  return seconds ? `${seconds.toFixed(1)} s` : 'Unknown'
}
</script>
