<template>
  <section ref="panel" class="preview-panel" aria-label="Diyagram önizlemesi">
    <n-flex align="center" justify="space-between" class="preview-tools">
      <n-text strong>Önizleme</n-text>
      <n-flex :size="4">
        <n-button size="small" aria-label="Uzaklaştır" @click="view('out')">−</n-button>
        <n-button size="small" aria-label="Gerçek boyuta dön" @click="view('actual')"
          >{{ Math.round(scale * 100) }}%</n-button
        >
        <n-button size="small" aria-label="Yakınlaştır" @click="view('in')">+</n-button>
        <n-button size="small" @click="view('fit')">Sığdır</n-button>
        <n-button size="small" @click="fullscreen">Tam ekran</n-button>
      </n-flex>
    </n-flex>
    <div class="frame-container">
      <iframe
        ref="frame"
        :srcdoc="documentSource"
        sandbox="allow-scripts"
        title="Yalıtılmış Mermaid diyagramı"
        referrerpolicy="no-referrer"
      />
      <div v-if="!hasDrawing" class="empty-preview">
        <n-text depth="3">{{
          busy ? 'Diyagram çiziliyor…' : 'Mermaid kodu yazın veya bir şablon ekleyin.'
        }}</n-text>
      </div>
    </div>
    <n-flex justify="space-between" align="center" class="preview-status">
      <span role="status" aria-live="polite">{{ statusText }}</span>
      <n-button v-if="failed" size="tiny" @click="restart">Motoru yeniden başlat</n-button>
    </n-flex>
  </section>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useThemeVars } from 'naive-ui'
import rendererUrl from '../../../../.cache/mermaid/renderer.js?url'
import { createRendererDocument, isRendererMessage } from '../services/rendererProtocol'
import type { MermaidDiagram } from '../models/project'

const props = defineProps<{ diagram: MermaidDiagram; live: boolean }>()
const emit = defineEmits<{
  status: [
    value: {
      canExport: boolean
      busy: boolean
      error: string
      line: number
      width: number
      height: number
    }
  ]
}>()
const themeVars = useThemeVars()
const panel = ref<HTMLElement>(),
  frame = ref<HTMLIFrameElement>()
const channel = ref(crypto.randomUUID()),
  ready = ref(false),
  failed = ref(false),
  busy = ref(false),
  hasDrawing = ref(false)
const error = ref(''),
  errorLine = ref(0),
  scale = ref(1),
  width = ref(0),
  height = ref(0),
  validRevision = ref(-1),
  revision = ref(0)
const pending = new Map<
  string,
  {
    revision: number
    resolve: (blob: Blob) => void
    reject: (error: Error) => void
    timer: ReturnType<typeof setTimeout>
  }
>()
let drawTimer: ReturnType<typeof setTimeout> | undefined,
  timeout: ReturnType<typeof setTimeout> | undefined
const documentSource = computed(() =>
  createRendererDocument(
    new URL(rendererUrl, window.location.href).href,
    channel.value,
    window.location.origin
  )
)
const canExport = computed(
  () => ready.value && validRevision.value === revision.value && hasDrawing.value
)
const statusText = computed(() =>
  error.value
    ? hasDrawing.value
      ? 'Son geçerli çizim gösteriliyor · Kodda hata var'
      : 'Diyagram çizilemedi'
    : busy.value
      ? 'Diyagram çiziliyor…'
      : canExport.value
        ? 'Çizim hazır'
        : hasDrawing.value
          ? 'Kod değişti · Önizleme güncel değil'
          : 'Çizim bekleniyor'
)
watch(
  [canExport, busy, error, errorLine, width, height],
  () =>
    emit('status', {
      canExport: canExport.value,
      busy: busy.value,
      error: error.value,
      line: errorLine.value,
      width: width.value,
      height: height.value
    }),
  { immediate: true }
)
function post(data: object) {
  if (ready.value) frame.value?.contentWindow?.postMessage({ channel: channel.value, ...data }, '*')
}
function startTimeout() {
  clearTimeout(timeout)
  timeout = setTimeout(() => {
    failed.value = true
    busy.value = false
    error.value = 'Çizim motoru yanıt vermedi. Motoru yeniden başlatın.'
    validRevision.value = -1
  }, 20000)
}
function render() {
  clearTimeout(drawTimer)
  if (!ready.value || !props.diagram.code.trim()) return
  busy.value = true
  error.value = ''
  errorLine.value = 0
  validRevision.value = -1
  post({
    type: 'render',
    revision: revision.value,
    code: props.diagram.code,
    theme: props.diagram.theme
  })
  startTimeout()
}
function rejectExports() {
  pending.forEach((item) => {
    clearTimeout(item.timer)
    item.reject(new Error('Dışa aktarım sırasında şema değişti. Yeniden deneyin.'))
  })
  pending.clear()
}
watch(
  [() => props.diagram.id, () => props.diagram.code, () => props.diagram.theme],
  (next, previous) => {
    revision.value++
    validRevision.value = -1
    error.value = ''
    errorLine.value = 0
    busy.value = false
    clearTimeout(drawTimer)
    clearTimeout(timeout)
    rejectExports()
    const clear = !previous || next[0] !== previous[0] || !next[1].trim()
    if (clear) hasDrawing.value = false
    post({ type: 'invalidate', revision: revision.value, clear })
    if (props.live || clear) drawTimer = setTimeout(render, 420)
  },
  { immediate: true, flush: 'sync' }
)
watch(
  () => props.live,
  (value) => {
    clearTimeout(drawTimer)
    if (value) render()
  }
)
function onMessage(event: MessageEvent) {
  if (!isRendererMessage(event, frame.value?.contentWindow || null, channel.value)) return
  const data = event.data
  if (data.type === 'ready') {
    ready.value = true
    failed.value = false
    clearTimeout(timeout)
    render()
    return
  }
  if (data.type === 'viewport') {
    scale.value = data.scale
    return
  }
  if (data.revision !== revision.value) return
  if (data.type === 'rendered') {
    clearTimeout(timeout)
    busy.value = false
    failed.value = false
    hasDrawing.value = true
    width.value = data.width
    height.value = data.height
    validRevision.value = data.revision
  } else if (data.type === 'error') {
    clearTimeout(timeout)
    busy.value = false
    error.value = data.message
    errorLine.value = data.line
  } else if (data.type === 'exported' || data.type === 'export-error') {
    const request = pending.get(data.requestId)
    if (!request || request.revision !== data.revision) return
    clearTimeout(request.timer)
    pending.delete(data.requestId)
    if (data.type === 'export-error') request.reject(new Error(data.message))
    else
      request.resolve(
        new Blob([data.bytes], {
          type: data.format === 'svg' ? 'image/svg+xml;charset=utf-8' : 'image/png'
        })
      )
  }
}
function requestExport(format: 'svg' | 'png', factor: number, transparent: boolean): Promise<Blob> {
  if (!canExport.value) return Promise.reject(new Error('Önce güncel kodu başarıyla çizin.'))
  const requestId = crypto.randomUUID()
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      pending.delete(requestId)
      reject(new Error('Görsel hazırlanamadı. Yeniden deneyin.'))
    }, 25000)
    pending.set(requestId, { revision: revision.value, resolve, reject, timer })
    post({ type: 'export', requestId, revision: revision.value, format, factor, transparent })
  })
}
function view(action: string) {
  post({ type: 'view', action })
}
async function fullscreen() {
  try {
    if (document.fullscreenElement) await document.exitFullscreen()
    else await panel.value?.requestFullscreen()
  } catch {
    error.value = 'Bu ortam tam ekranı desteklemiyor.'
  }
}
function restart() {
  rejectExports()
  ready.value = false
  failed.value = false
  hasDrawing.value = false
  channel.value = crypto.randomUUID()
  startTimeout()
}
window.addEventListener('message', onMessage)
startTimeout()
onBeforeUnmount(() => {
  clearTimeout(drawTimer)
  clearTimeout(timeout)
  rejectExports()
  window.removeEventListener('message', onMessage)
})
defineExpose({ render, requestExport })
</script>

<style scoped>
.preview-panel {
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 460px;
  background: v-bind('themeVars.cardColor');
  border: 1px solid v-bind('themeVars.borderColor');
  border-radius: v-bind('themeVars.borderRadius');
  overflow: hidden;
}
.preview-tools {
  padding: 10px;
  border-bottom: 1px solid v-bind('themeVars.borderColor');
}
.frame-container {
  position: relative;
  flex: 1;
  min-height: 360px;
}
iframe {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  border: 0;
}
.empty-preview {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  text-align: center;
  padding: 20px;
  pointer-events: none;
  background: v-bind('themeVars.cardColor');
}
.preview-status {
  min-height: 28px;
  padding: 6px 10px;
  font-size: 12px;
  color: v-bind('themeVars.textColor2');
  border-top: 1px solid v-bind('themeVars.borderColor');
}
.preview-panel:fullscreen {
  height: 100dvh;
  border: 0;
  border-radius: 0;
}
@media (max-width: 600px) {
  .preview-tools :deep(.n-button) {
    min-height: 44px;
  }
}
</style>
