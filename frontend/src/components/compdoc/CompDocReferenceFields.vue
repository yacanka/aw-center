<template>
  <n-card title="References" size="small">
    <n-grid responsive="self" item-responsive :x-gap="12" :y-gap="4" :cols="48">
      <n-form-item-gi span="0:48 700:30" path="tech_doc_no" label="Tech Doc No">
        <n-input
          v-model:value="compdoc.tech_doc_no"
          :readonly="readonly"
          :status="changed('tech_doc_no')"
          @keydown.enter.prevent
        />
      </n-form-item-gi>
      <n-form-item-gi span="0:48 700:9" path="tech_doc_issue" label="Issue">
        <n-input
          v-model:value="compdoc.tech_doc_issue"
          :readonly="readonly"
          :status="changed('tech_doc_issue')"
          @keydown.enter.prevent
        />
      </n-form-item-gi>
      <n-form-item-gi span="0:48 700:9" path="delivered_tech_doc_issue" label="Delivered">
        <n-input
          v-model:value="compdoc.delivered_tech_doc_issue"
          :readonly="readonly"
          :status="changed('delivered_tech_doc_issue')"
          @keydown.enter.prevent
        />
      </n-form-item-gi>
      <template v-if="hasExtraFields">
        <n-form-item-gi span="0:48 700:30" path="tech_doc_no_2" label="Tech Doc No 2">
          <n-input
            v-model:value="compdoc.tech_doc_no_2"
            :readonly="readonly"
            :status="changed('tech_doc_no_2')"
          />
        </n-form-item-gi>
        <n-form-item-gi span="0:48 700:9" path="tech_doc_issue_2" label="Issue 2">
          <n-input
            v-model:value="compdoc.tech_doc_issue_2"
            :readonly="readonly"
            :status="changed('tech_doc_issue_2')"
          />
        </n-form-item-gi>
        <n-form-item-gi span="0:48 700:9" path="delivered_tech_doc_issue_2" label="Delivered 2">
          <n-input
            v-model:value="compdoc.delivered_tech_doc_issue_2"
            :readonly="readonly"
            :status="changed('delivered_tech_doc_issue_2')"
          />
        </n-form-item-gi>
      </template>
      <n-form-item-gi span="0:48 700:8" path="cat" label="Cat">
        <n-select
          v-model:value="compdoc.cat"
          :options="catOptions"
          clearable
          :disabled="readonly"
          :status="changed('cat')"
        />
      </n-form-item-gi>
      <n-form-item-gi span="0:48 700:8" path="moc" label="MoC">
        <n-select
          v-model:value="compdoc.moc"
          :options="mocOptions"
          clearable
          :disabled="readonly"
          :status="changed('moc')"
        />
      </n-form-item-gi>
      <n-form-item-gi span="0:48 700:32" path="mom_no" label="MoM No">
        <n-input
          v-model:value="compdoc.mom_no"
          type="textarea"
          :autosize="{ minRows: 1, maxRows: 3 }"
          :readonly="readonly"
          :status="changed('mom_no')"
        />
      </n-form-item-gi>
      <n-form-item-gi span="48" path="requirements" label="Requirements">
        <n-dynamic-tags v-model:value="compdoc.requirements" :disabled="readonly" />
      </n-form-item-gi>
      <n-form-item-gi span="48" path="path" label="Reference Path">
        <n-input
          v-model:value="compdoc.path"
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
import type { ICompDoc } from '@/models/compdocs'
import { catOptions, mocOptions } from '@/services/compdocCatalog'

const props = defineProps<{
  compdoc: ICompDoc
  original: ICompDoc
  readonly: boolean
  hasExtraFields: boolean
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
