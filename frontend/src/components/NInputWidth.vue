<template>
  <span class="auto-width-input">
    <n-input
      ref="inputReference"
      v-bind="$attrs"
      :value="value"
      :placeholder="placeholder"
      :size="size"
      :style="inputStyle"
      @blur="emitBlur"
      @update:value="updateValue"
    />
    <span ref="measureReference" class="measure-span" :style="measureStyle">{{
      measuredText
    }}</span>
  </span>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'

defineOptions({ inheritAttrs: false })

type InputSize = 'tiny' | 'small' | 'medium' | 'large'

const props = withDefaults(
  defineProps<{
    value?: string
    size?: InputSize
    placeholder?: string
    autofocus?: boolean
  }>(),
  {
    value: '',
    size: 'medium',
    placeholder: 'Input',
    autofocus: false
  }
)

const emit = defineEmits<{
  'update:value': [value: string]
  change: [value: string]
  blur: []
}>()

const sizeSettings: Record<InputSize, { fontSize: number; offsetWidth: number }> = {
  tiny: { fontSize: 12, offsetWidth: 22 },
  small: { fontSize: 14, offsetWidth: 28 },
  medium: { fontSize: 14, offsetWidth: 32 },
  large: { fontSize: 15, offsetWidth: 36 }
}

const inputWidth = ref(48)
const inputReference = ref<{ focus: () => void } | null>(null)
const measureReference = ref<HTMLElement | null>(null)
const settings = computed(() => sizeSettings[props.size])
const measuredText = computed(() => props.value || props.placeholder)
const inputStyle = computed(() => ({ width: `${inputWidth.value}px` }))
const measureStyle = computed(() => ({ fontSize: `${settings.value.fontSize}px` }))

watch(
  () => [props.value, props.placeholder, props.size],
  () => resizeInput()
)

function updateValue(value: string) {
  emit('update:value', value)
  emit('change', value)
  resizeInput()
}

function emitBlur() {
  emit('blur')
}

function resizeInput() {
  nextTick(() => {
    inputWidth.value = calculateInputWidth()
  })
}

function calculateInputWidth() {
  const textWidth = measureReference.value?.offsetWidth || 0
  return Math.max(48, textWidth + settings.value.offsetWidth)
}

onMounted(() => {
  resizeInput()
  if (props.autofocus) inputReference.value?.focus()
})
</script>

<style scoped>
.auto-width-input {
  display: inline-block;
  position: relative;
}

.measure-span {
  font-family: inherit;
  left: 0;
  margin: 0;
  padding: 0;
  position: absolute;
  top: 0;
  visibility: hidden;
  white-space: pre;
}
</style>
