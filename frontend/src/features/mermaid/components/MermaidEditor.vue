<template>
  <section class="editor-panel" aria-label="Kod düzenleyici">
    <div class="editor-body">
      <pre
        class="gutter"
        aria-hidden="true"
      ><span :style="{ transform: `translateY(${-scrollTop}px)` }">{{ lineNumbers }}</span></pre>
      <div class="editor-field">
        <pre
          class="highlight"
          aria-hidden="true"
          :style="{ transform: `translate(${-scrollLeft}px,${-scrollTop}px)` }"
          v-html="highlightedSource(modelValue)"
        />
        <textarea
          ref="input"
          :value="modelValue"
          aria-label="Mermaid kodu"
          aria-describedby="mermaid-editor-hint"
          wrap="off"
          spellcheck="false"
          autocapitalize="off"
          autocomplete="off"
          @input="onInput"
          @scroll="syncScroll"
          @keydown="onKeydown"
          @click="updateCursor"
          @keyup="updateCursor"
          @select="updateCursor"
          @compositionstart="composing = true"
          @compositionend="finishComposition"
        />
      </div>
    </div>
    <n-flex justify="space-between" align="center" class="editor-footer">
      <span>Satır {{ cursor.line }} · Sütun {{ cursor.column }}</span>
      <span
        >{{ modelValue.split('\n').length }} satır ·
        {{ modelValue.length.toLocaleString('tr-TR') }} karakter</span
      >
    </n-flex>
    <span id="mermaid-editor-hint" class="sr-only"
      >Tab dört boşluk girer. Editörden çıkmak için Escape, ardından Tab tuşuna basın.</span
    >
  </section>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { useThemeVars } from 'naive-ui'
import { highlightedSource } from '../services/sourceText'

const props = defineProps<{ modelValue: string; diagramId: string }>()
const emit = defineEmits<{ 'update:modelValue': [value: string]; undo: []; redo: []; render: [] }>()
const themeVars = useThemeVars(),
  input = ref<HTMLTextAreaElement>()
const scrollTop = ref(0),
  scrollLeft = ref(0),
  cursor = ref({ line: 1, column: 1 })
const positions = new Map<string, { start: number; end: number; top: number; left: number }>()
const lineNumbers = computed(() =>
  Array.from({ length: props.modelValue.split('\n').length }, (_, index) => index + 1).join('\n')
)
let releaseTab = false
const composing = ref(false)
function syncScroll() {
  scrollTop.value = input.value?.scrollTop || 0
  scrollLeft.value = input.value?.scrollLeft || 0
}
function updateCursor() {
  const before = props.modelValue.slice(0, input.value?.selectionStart || 0)
  cursor.value = {
    line: before.split('\n').length,
    column: before.length - before.lastIndexOf('\n')
  }
}
function onInput() {
  if (!composing.value && input.value) emit('update:modelValue', input.value.value)
  updateCursor()
}
function finishComposition() {
  composing.value = false
  onInput()
}
function replace(
  text: string,
  start = input.value!.selectionStart,
  end = input.value!.selectionEnd
) {
  input.value!.setRangeText(text, start, end, 'end')
  onInput()
}
function indent(outdent: boolean) {
  const element = input.value!,
    start = element.selectionStart,
    end = element.selectionEnd,
    text = element.value
  if (!outdent && start === end) {
    replace('    ')
    return
  }
  const first = text.lastIndexOf('\n', start - 1) + 1,
    last = end > start && text[end - 1] === '\n' ? end - 1 : end
  const breakAt = text.indexOf('\n', last),
    finish = breakAt < 0 ? text.length : breakAt
  const section = text.slice(first, finish),
    lines = section.split('\n')
  const removed = outdent ? lines[0].match(/^(?: {1,4}|\t)/)?.[0].length || 0 : -4
  const replacement = lines
    .map((line) => (outdent ? line.replace(/^(?: {1,4}|\t)/, '') : '    ' + line))
    .join('\n')
  element.setRangeText(replacement, first, finish, 'preserve')
  element.setSelectionRange(
    Math.max(first, start - removed),
    Math.max(first, end + replacement.length - section.length)
  )
  onInput()
}
function onKeydown(event: KeyboardEvent) {
  if (event.isComposing || composing.value) return
  if (event.key === 'Escape') {
    releaseTab = true
    return
  }
  if (event.key === 'Tab') {
    if (releaseTab) {
      releaseTab = false
      return
    }
    event.preventDefault()
    indent(event.shiftKey)
    return
  }
  releaseTab = false
  if ((event.ctrlKey || event.metaKey) && ['z', 'y'].includes(event.key.toLowerCase())) {
    event.preventDefault()
    if (event.key.toLowerCase() === 'y' || event.shiftKey) emit('redo')
    else emit('undo')
    return
  }
  if (event.key === 'Enter' && !event.ctrlKey && !event.metaKey && !event.shiftKey) {
    event.preventDefault()
    const line = input.value!.value.slice(0, input.value!.selectionStart).split('\n').pop()!
    replace('\n' + (line.match(/^\s*/)?.[0] || ''))
  }
}
watch(
  () => props.diagramId,
  async (id, old) => {
    if (input.value && old)
      positions.set(old, {
        start: input.value.selectionStart,
        end: input.value.selectionEnd,
        top: input.value.scrollTop,
        left: input.value.scrollLeft
      })
    await nextTick()
    const saved = positions.get(id)
    input.value?.setSelectionRange(saved?.start || 0, saved?.end || 0)
    if (input.value) {
      input.value.scrollTop = saved?.top || 0
      input.value.scrollLeft = saved?.left || 0
    }
    syncScroll()
    updateCursor()
  }
)
function goToLine(line: number) {
  const lines = props.modelValue.split('\n'),
    index = Math.max(0, Math.min(lines.length - 1, line - 1))
  const start = lines.slice(0, index).join('\n').length + (index ? 1 : 0)
  input.value?.focus()
  input.value?.setSelectionRange(start, start + lines[index].length)
  if (input.value) input.value.scrollTop = Math.max(0, (index - 2) * 24)
  syncScroll()
  updateCursor()
}
function resetInput() {
  if (input.value) input.value.value = props.modelValue
}
defineExpose({ goToLine, resetInput })
</script>

<style scoped>
.editor-panel {
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 460px;
  border: 1px solid v-bind('themeVars.borderColor');
  border-radius: v-bind('themeVars.borderRadius');
  background: v-bind('themeVars.codeColor');
  overflow: hidden;
}
.editor-body {
  display: flex;
  position: relative;
  flex: 1;
  min-height: 380px;
  overflow: hidden;
}
.gutter {
  flex: 0 0 44px;
  box-sizing: border-box;
  margin: 0;
  padding: 12px 8px;
  text-align: right;
  color: v-bind('themeVars.textColor3');
  border-right: 1px solid v-bind('themeVars.borderColor');
  overflow: hidden;
}
.gutter span {
  display: block;
}
.editor-field {
  position: relative;
  min-width: 0;
  flex: 1;
  overflow: hidden;
}
.highlight,
textarea,
.gutter {
  font-family: monospace;
  font-size: 14px;
  line-height: 24px;
  tab-size: 4;
}
.highlight,
textarea {
  box-sizing: border-box;
  margin: 0;
  padding: 12px;
  white-space: pre;
  border: 0;
}
.highlight {
  position: absolute;
  left: 0;
  top: 0;
  min-width: 100%;
  color: v-bind('themeVars.textColor1');
  pointer-events: none;
}
textarea {
  position: absolute;
  inset: 0;
  resize: none;
  width: 100%;
  height: 100%;
  background: transparent;
  color: transparent;
  caret-color: v-bind('themeVars.textColor1');
  overflow: auto;
  outline-offset: -2px;
}
textarea::selection {
  background: v-bind('themeVars.primaryColorSuppl');
  color: v-bind('themeVars.baseColor');
}
.highlight :deep(.syntax-keyword) {
  color: v-bind('themeVars.primaryColor');
  font-weight: 600;
}
.highlight :deep(.syntax-string) {
  color: v-bind('themeVars.warningColor');
}
.highlight :deep(.syntax-comment) {
  color: v-bind('themeVars.textColor3');
}
.highlight :deep(.syntax-arrow) {
  color: v-bind('themeVars.successColor');
}
.editor-footer {
  padding: 8px;
  font-size: 12px;
  color: v-bind('themeVars.textColor2');
  border-top: 1px solid v-bind('themeVars.borderColor');
}
.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip-path: inset(50%);
}
</style>
