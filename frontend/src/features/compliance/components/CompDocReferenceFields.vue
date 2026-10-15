<template>
  <n-card title="References" size="small">
    <n-grid responsive="self" item-responsive :x-gap="12" :y-gap="4" :cols="12">
      <n-form-item-gi span="0:12 700:9" path="number" label="Number">
        <n-input
          v-model:value="compdoc.number"
          maxlength="64"
          :readonly="readonly"
          :status="changed('number')"
          @keydown.enter.prevent
        />
      </n-form-item-gi>
      <n-form-item-gi span="0:12 700:3" path="issue" label="Issue">
        <n-input
          v-model:value="compdoc.issue"
          maxlength="255"
          :readonly="readonly"
          :status="changed('issue')"
          @keydown.enter.prevent
        />
      </n-form-item-gi>
      <n-form-item-gi span="0:12 700:2" path="cat" label="Cat">
        <n-input
          v-model:value="compdoc.cat"
          maxlength="12"
          :readonly="readonly"
          :status="changed('cat')"
          @keydown.enter.prevent
        />
      </n-form-item-gi>
      <n-form-item-gi span="0:12 700:2" path="moc" label="MoC">
        <n-select
          v-model:value="compdoc.moc"
          :options="mocOptions"
          clearable
          :disabled="readonly"
          :status="changed('moc')"
        />
      </n-form-item-gi>
      <n-form-item-gi span="0:12 700:8" path="mom_no" label="MoM No">
        <n-input
          v-model:value="compdoc.mom_no"
          maxlength="128"
          type="textarea"
          :autosize="{ minRows: 1, maxRows: 3 }"
          :readonly="readonly"
          :status="changed('mom_no')"
        />
      </n-form-item-gi>
      <n-form-item-gi span="12" path="requirements" label="Requirements">
        <n-dynamic-tags v-model:value="compdoc.requirements" :disabled="readonly" />
      </n-form-item-gi>
      <n-form-item-gi span="12" path="path" label="Reference Path">
        <n-input
          v-model:value="compdoc.path"
          maxlength="512"
          :readonly="readonly"
          :status="changed('path')"
          @click="readonly ? copyPath() : undefined"
          @keydown.enter.prevent
        />
      </n-form-item-gi>
    </n-grid>
  </n-card>
</template>

<script setup lang="ts">
import type { ICompDoc } from '@/features/compliance/models/compdocs'
import { mocOptions } from '@/features/compliance/api/compdocCatalog'

const props = defineProps<{
  compdoc: ICompDoc
  original: ICompDoc
  readonly: boolean
}>()

function changed(field: keyof ICompDoc): '' | 'warning' {
  return props.original[field] === props.compdoc[field] ? '' : 'warning'
}

async function copyPath(): Promise<void> {
  if (!props.compdoc.path) {
    window.$message.warning('Document path is unavailable.')
    return
  }
  try {
    await navigator.clipboard.writeText(props.compdoc.path)
    window.$message.success('Path copied')
  } catch {
    window.$message.error('The path could not be copied.')
  }
}
</script>
