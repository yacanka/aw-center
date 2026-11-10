<script setup lang="ts">
import { NAlert, NButton, NFormItem, NInput, NSpace, NText } from 'naive-ui'
import type { NumberingContextField } from '../api/compdocNumbering'
import { isDocumentKeyword } from '../composables/numberingContext'
defineProps<{
  fields: NumberingContextField[]
  values: Record<string, string>
  loading: boolean
  error: string
  disabled: boolean
  idPrefix: string
}>()
const emit = defineEmits<{ 'update:values': [value: Record<string, string>]; retry: [] }>()
function update(values: Record<string, string>, key: string, value: string) {
  emit('update:values', { ...values, [key]: value })
}
</script>
<template>
  <n-space vertical :size="12">
    <n-text v-if="loading" depth="3" role="status">Loading format fields…</n-text>
    <n-alert v-else-if="error" type="error" :bordered="false" role="alert">
      <n-space vertical>
        <span>{{ error }}</span>
        <n-button size="small" :disabled="disabled" @click="emit('retry')"
          >Retry loading fields</n-button
        >
      </n-space>
    </n-alert>
    <n-form-item
      v-for="(field, index) in fields"
      :key="`${field.key}-${index}`"
      :label="field.key"
      :label-props="{ for: `${idPrefix}-${index}` }"
      :required="field.required"
    >
      <n-input
        :value="values[field.key] || ''"
        :maxlength="field.max_length"
        :placeholder="
          isDocumentKeyword(field.key)
            ? 'From compliance document'
            : field.default === null
              ? field.key
              : String(field.default)
        "
        :disabled="disabled || isDocumentKeyword(field.key)"
        :input-props="{
          id: `${idPrefix}-${index}`,
          required: field.required,
          'aria-describedby': `${idPrefix}-${index}-hint`
        }"
        @update:value="update(values, field.key, $event)"
        @keydown.enter.prevent
      />
      <template #feedback>
        <span :id="`${idPrefix}-${index}-hint`">
          <template v-if="isDocumentKeyword(field.key)"
            >Filled automatically from each compliance document.
          </template>
          {{ field.max_length }} characters maximum.{{
            !field.required ? ` Default: ${field.default ?? '—'}.` : ''
          }}
        </span>
      </template>
    </n-form-item>
  </n-space>
</template>
