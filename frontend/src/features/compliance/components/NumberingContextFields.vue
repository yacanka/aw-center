<script setup lang="ts">
import type { NumberingContextField } from '../api/compdocNumbering'
defineProps<{
  fields: NumberingContextField[]
  values: Record<string, string>
  loading: boolean
  error: string
  disabled: boolean
  idPrefix: string
}>()
const emit = defineEmits<{ 'update:values': [value: Record<string, string>]; retry: [] }>()
function update(values: Record<string, string>, key: string, event: Event) {
  emit('update:values', { ...values, [key]: (event.target as HTMLInputElement).value })
}
</script>
<template>
  <div class="numbering-context">
    <p v-if="loading" role="status">Loading format fields…</p>
    <div v-else-if="error" role="alert">
      <p>{{ error }}</p>
      <n-button size="small" :disabled="disabled" @click="emit('retry')"
        >Retry loading fields</n-button
      >
    </div>
    <div v-for="(field, index) in fields" :key="`${field.key}-${index}`" class="context-field">
      <label :for="`${idPrefix}-${index}`"
        >{{ field.key }}{{ field.required ? ' (required)' : '' }}</label
      >
      <input
        :id="`${idPrefix}-${index}`"
        :value="values[field.key]"
        :required="field.required"
        :maxlength="field.max_length"
        :placeholder="field.default === null ? field.key : String(field.default)"
        :disabled="disabled"
        :aria-describedby="`${idPrefix}-${index}-hint`"
        @input="update(values, field.key, $event)"
        @keydown.enter.prevent
      />
      <small :id="`${idPrefix}-${index}-hint`"
        >{{ field.max_length }} characters maximum.{{
          !field.required ? ` Default: ${field.default ?? '—'}.` : ''
        }}</small
      >
    </div>
  </div>
</template>
<style scoped>
.numbering-context {
  display: grid;
  gap: 12px;
}
.context-field {
  display: grid;
  gap: 6px;
}
label {
  font-weight: 600;
}
input {
  width: 100%;
  box-sizing: border-box;
  border: 1px solid #8c8c94;
  border-radius: 0;
  padding: 10px;
  font: inherit;
  background: #ffffff;
  color: #171717;
}
input:focus-visible {
  outline: 2px solid #002fa7;
  outline-offset: 2px;
}
input:disabled {
  opacity: 0.6;
}
small {
  line-height: 1.5;
}
p {
  margin: 0;
}
</style>
