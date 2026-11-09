<template>
  <div class="mermaid-workshop" @dragover.prevent @drop.prevent="dropFile">
    <n-card title="Mermaid Atölyesi">
      <template #header-extra><n-button @click="helpVisible = true">Yardım</n-button></template>
      <n-flex align="center" justify="space-between">
        <n-flex align="center" class="project-name">
          <n-input
            v-model:value="projectName"
            :maxlength="180"
            :input-props="{ 'aria-label': 'Proje adı' }"
            @update:value="renameProject"
            @blur="projectName = project.name"
          />
          <n-tag :type="dirty ? 'warning' : 'default'" size="small">{{
            dirty ? 'Dosyaya kaydedilmedi' : '.mmdproj'
          }}</n-tag>
        </n-flex>
        <n-flex>
          <n-button @click="newProject">Yeni proje</n-button>
          <n-button @click="fileInput?.click()">Proje aç</n-button>
          <n-button @click="saveProject">Projeyi kaydet</n-button>
          <n-button
            type="primary"
            :disabled="!previewStatus.canExport"
            @click="exportVisible = true"
            >Görsel aktar</n-button
          >
        </n-flex>
      </n-flex>
      <n-flex align="center" justify="space-between" class="toolbar">
        <n-button @click="templatesVisible = true">Şablon ekle</n-button>
        <n-text depth="3">Kod ve çizimler bu tarayıcıda işlenir.</n-text>
      </n-flex>
      <n-alert v-if="storageError" type="warning" :bordered="false" class="storage-warning">{{
        storageError
      }}</n-alert>
      <n-flex align="center" :wrap="false">
        <div role="tablist" aria-label="Şema sekmeleri" class="diagram-tabs" @keydown="tabKeydown">
          <div v-for="diagram in project.diagrams" :key="diagram.id" class="diagram-tab">
            <n-button
              :id="`mermaid-tab-${diagram.id}`"
              role="tab"
              :aria-selected="diagram.id === active.id"
              aria-controls="mermaid-workspace"
              :tabindex="diagram.id === active.id ? 0 : -1"
              :type="diagram.id === active.id ? 'primary' : 'default'"
              secondary
              @click="selectDiagram(diagram.id)"
              @dblclick="titleInput?.focus()"
              >{{ diagram.title }}</n-button
            >
            <n-button
              size="small"
              :aria-label="`${diagram.title} şemasını kaldır`"
              @click="confirmRemove(diagram.id)"
              >×</n-button
            >
          </div>
        </div>
        <n-button @click="addDiagram()">Şema ekle</n-button>
      </n-flex>
      <n-flex align="center" justify="space-between" class="diagram-toolbar">
        <n-input
          ref="titleInput"
          v-model:value="diagramTitle"
          class="diagram-title"
          :input-props="{ 'aria-label': 'Şema başlığı' }"
          :maxlength="180"
          @update:value="renameDiagram"
          @blur="diagramTitle = active.title"
        />
        <n-flex align="center">
          <n-select
            :value="active.theme"
            filterable
            :input-props="{ 'aria-label': 'Şema teması', role: 'combobox' }"
            :options="themeOptions"
            aria-label="Şema teması"
            class="theme-select"
            @update:value="state.setTheme"
          />
          <n-switch v-model:value="live" aria-label="Canlı önizleme"
            ><template #checked>Canlı</template><template #unchecked>Elle</template></n-switch
          >
          <n-button :loading="previewStatus.busy" @click="preview?.render()">Çiz</n-button>
          <n-button @click="copyCode">Kodu kopyala</n-button>
          <n-button :disabled="!canUndo" aria-label="Geri al" @click="state.undo">Geri al</n-button>
          <n-button :disabled="!canRedo" aria-label="Yinele" @click="state.redo">Yinele</n-button>
        </n-flex>
      </n-flex>
      <div
        id="mermaid-workspace"
        ref="workspace"
        class="workspace"
        role="tabpanel"
        :aria-labelledby="`mermaid-tab-${active.id}`"
        :style="{ '--editor-width': `${editorWidth}%` }"
      >
        <MermaidEditor
          :key="userId"
          ref="editor"
          :diagram-id="active.id"
          :model-value="active.code"
          @update:model-value="editCode"
          @undo="state.undo"
          @redo="state.redo"
        />
        <div
          class="resizer"
          role="separator"
          tabindex="0"
          aria-label="Editör genişliği"
          aria-orientation="vertical"
          aria-valuemin="25"
          aria-valuemax="65"
          :aria-valuenow="Math.round(editorWidth)"
          @keydown="resizeKeyboard"
          @pointerdown="startResize"
          @pointermove="resizePointer"
          @pointerup="stopResize"
          @pointercancel="stopResize"
          @lostpointercapture="stopResize"
        />
        <MermaidPreview
          :key="userId"
          ref="preview"
          :diagram="active"
          :live="live"
          @status="previewStatus = $event"
        />
      </div>
      <n-alert v-if="previewStatus.error" type="error" :bordered="false" class="render-error">
        <pre>{{ previewStatus.error }}</pre>
        <n-button
          v-if="previewStatus.line > 0"
          size="small"
          @click="editor?.goToLine(previewStatus.line)"
          >Hatalı satıra git</n-button
        >
      </n-alert>
      <n-flex justify="space-between" class="workspace-footer">
        <n-text depth="3"
          >{{ project.diagrams.length }} şemalı proje · Otomatik yerel taslak</n-text
        >
        <n-text depth="3">Ctrl/Cmd+S: kaydet · Ctrl/Cmd+Enter: çiz</n-text>
      </n-flex>
    </n-card>

    <input
      ref="fileInput"
      type="file"
      accept=".mmdproj,.json,application/json"
      hidden
      @change="chooseFile"
    />
    <n-modal
      v-model:show="templatesVisible"
      preset="card"
      title="Şablon ekle"
      class="workshop-dialog"
    >
      <n-text depth="3">Seçtiğiniz şablon ayrı bir şema sekmesine eklenir.</n-text>
      <div class="template-grid">
        <n-button
          v-for="template in templates"
          :key="template.id"
          class="template-button"
          @click="addTemplate(template)"
          ><span
            ><strong>{{ template.label }}</strong
            ><small>{{ template.description }}</small></span
          ></n-button
        >
      </div>
    </n-modal>
    <n-modal
      v-model:show="exportVisible"
      preset="card"
      title="Görsel aktar"
      class="workshop-dialog"
    >
      <n-form label-placement="top">
        <n-form-item label="Dosya biçimi"
          ><n-select
            v-model:value="exportFormat"
            filterable
            :input-props="{ 'aria-label': 'Dosya biçimi', role: 'combobox' }"
            :options="[
              { label: 'SVG · Vektörel', value: 'svg' },
              { label: 'PNG · Görsel', value: 'png' }
            ]"
            aria-label="Dosya biçimi"
        /></n-form-item>
        <n-form-item v-if="exportFormat === 'png'" label="Çözünürlük"
          ><n-select
            v-model:value="exportScale"
            filterable
            :input-props="{ 'aria-label': 'Çözünürlük', role: 'combobox' }"
            :options="[
              { label: '1× · Standart', value: 1 },
              { label: '2× · Yüksek', value: 2 },
              { label: '3× · Çok yüksek', value: 3 }
            ]"
            aria-label="Çözünürlük"
        /></n-form-item>
        <n-checkbox v-model:checked="transparent">Şeffaf arka plan</n-checkbox>
        <n-p
          >{{ safeName(active.title) }}.{{ exportFormat }} ·
          {{ Math.ceil(previewStatus.width * (exportFormat === 'png' ? exportScale : 1)) }} ×
          {{ Math.ceil(previewStatus.height * (exportFormat === 'png' ? exportScale : 1)) }}</n-p
        >
        <n-button
          type="primary"
          :loading="exporting"
          :disabled="!previewStatus.canExport"
          @click="exportDiagram"
          >{{ exportFormat.toUpperCase() }} indir</n-button
        >
      </n-form>
    </n-modal>
    <n-modal
      v-model:show="helpVisible"
      preset="card"
      title="Mermaid Atölyesi kullanımı"
      class="workshop-dialog"
    >
      <n-p
        >Bir proje içinde birden fazla bağımsız şema düzenleyebilirsiniz. Her sekmenin kodu, teması
        ve bu oturumdaki geri alma geçmişi ayrıdır. Şema başlığını üstteki alandan veya F2 ile
        düzenleyin.</n-p
      >
      <n-p
        >Projeyi kaydet, tüm şemaları .mmdproj dosyasına indirir. Proje aç veya sürükleyip bırak ile
        dosyanızı yeniden açabilirsiniz. Görsel aktar yalnız seçili şemayı indirir.</n-p
      >
      <n-p
        >Taslak yalnız bu tarayıcıda, hesabınıza ayrılmış alanda saklanır. Taşınabilir bir kopya
        için dosya indirin. Tarayıcı verilerinin silinmesi yerel taslağı kaldırır.</n-p
      >
      <n-p
        >Ctrl/Cmd+S: proje dosyası · Ctrl/Cmd+Enter: çiz · Ctrl/Cmd+Z: geri al · Ctrl/Cmd+Shift+Z
        veya Ctrl/Cmd+Y: yinele · Tab/Shift+Tab: girinti · Escape ardından Tab: editörden
        çıkış.</n-p
      >
      <n-p
        >Önizlemeyi sürükleyerek veya ok tuşlarıyla taşıyın. Ctrl/Cmd+tekerlek veya +/− ile
        yakınlaştırın; 0 ile sığdırın. Editör genişliğini ayırıcı üzerinde sağ/sol oklarla
        değiştirebilirsiniz.</n-p
      >
      <n-p
        >Mermaid 12.3.0 · Çizim motoru yalıtılmış olarak çalışır. Haricî görseller ve çevrimiçi ikon
        paketleri yüklenmez. AW Center oturumu gerekir.</n-p
      >
      <details>
        <summary>Açık kaynak lisansları</summary>
        <pre class="licenses">{{ licenses }}</pre>
      </details>
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { useDialog, useMessage, useThemeVars, type DialogReactive, type InputInst } from 'naive-ui'
import MermaidEditor from '../components/MermaidEditor.vue'
import MermaidPreview from '../components/MermaidPreview.vue'
import { useMermaidProject } from '../composables/useMermaidProject'
import { createProject, serializeProject, type MermaidProject } from '../models/project'
import { templates } from '../models/templates'
import { safeName } from '../services/sourceText'
import { saveBlobAsFile } from '@/shared/services/download'
import { useSessionStore } from '@/features/session/stores/session'
import licenses from '../THIRD_PARTY_NOTICES.txt?raw'

const themeVars = useThemeVars(),
  dialog = useDialog(),
  message = useMessage(),
  session = useSessionStore()
const userId = computed(() => session.getUser.id)
const confirmations = new Set<DialogReactive>()
let disposed = false
const state = useMermaidProject(userId)
const { project, active, dirty, live, editorWidth, storageError, canUndo, canRedo } = state
const projectName = ref(project.value.name),
  diagramTitle = ref(active.value.title)
const editor = ref<InstanceType<typeof MermaidEditor>>(),
  preview = ref<InstanceType<typeof MermaidPreview>>(),
  titleInput = ref<InputInst>()
const fileInput = ref<HTMLInputElement>(),
  workspace = ref<HTMLElement>()
const templatesVisible = ref(false),
  helpVisible = ref(false),
  exportVisible = ref(false),
  exporting = ref(false)
const exportFormat = ref<'svg' | 'png'>('svg'),
  exportScale = ref(2),
  transparent = ref(false)
const previewStatus = ref({
  canExport: false,
  busy: false,
  error: '',
  line: 0,
  width: 0,
  height: 0
})
const themeOptions = [
  { label: 'Atölye', value: 'studio' },
  { label: 'Klasik', value: 'default' },
  { label: 'Orman', value: 'forest' },
  { label: 'Gece', value: 'dark' },
  { label: 'Sade', value: 'neutral' }
]
watch(
  () => project.value,
  (value) => {
    cancelConfirmations()
    projectName.value = value.name
  }
)
watch(active, (value) => {
  diagramTitle.value = value.title
})
watch(
  userId,
  () => {
    cancelConfirmations()
    templatesVisible.value = false
    helpVisible.value = false
    exportVisible.value = false
    previewStatus.value = { canExport: false, busy: false, error: '', line: 0, width: 0, height: 0 }
  },
  { flush: 'sync' }
)
function report(error: unknown) {
  message.error(error instanceof Error ? error.message : 'İşlem tamamlanamadı.')
}
function editCode(value: string) {
  try {
    state.editCode(value)
  } catch (error) {
    report(error)
    editor.value?.resetInput()
  }
}
function renameProject(value: string) {
  try {
    state.renameProject(value)
  } catch (error) {
    report(error)
    projectName.value = project.value.name
  }
}
function renameDiagram(value: string) {
  try {
    state.renameDiagram(value)
  } catch (error) {
    report(error)
    diagramTitle.value = active.value.title
  }
}
function selectDiagram(id: string | number) {
  state.selectDiagram(String(id))
}
async function tabKeydown(event: KeyboardEvent) {
  if (
    (event.target as HTMLElement).getAttribute('role') !== 'tab' ||
    !['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)
  )
    return
  event.preventDefault()
  const diagrams = project.value.diagrams,
    index = diagrams.findIndex((item) => item.id === active.value.id)
  const next =
    event.key === 'Home'
      ? 0
      : event.key === 'End'
        ? diagrams.length - 1
        : (index + (event.key === 'ArrowRight' ? 1 : -1) + diagrams.length) % diagrams.length
  selectDiagram(diagrams[next].id)
  await nextTick()
  document.getElementById(`mermaid-tab-${active.value.id}`)?.focus()
}
function addDiagram(code = '', title?: string) {
  try {
    state.addDiagram(code, title)
  } catch (error) {
    report(error)
  }
}
function addTemplate(template: (typeof templates)[number]) {
  addDiagram(template.code, template.label)
  templatesVisible.value = false
}
function confirmRemove(id: string | number) {
  const item = project.value.diagrams.find((diagram) => diagram.id === id)
  if (!item) return
  confirmAction(
    'Şema kaldırılsın mı?',
    `“${item.title}” ve içindeki kod projeden kaldırılacak.`,
    'Kaldır',
    () => state.removeDiagram(item.id)
  )
}
function cancelConfirmations() {
  confirmations.forEach((confirmation) => confirmation.destroy())
  confirmations.clear()
}
function confirmAction(title: string, content: string, positiveText: string, action: () => void) {
  const owner = userId.value,
    currentProject = project.value,
    revision = state.revision.value
  const confirmation = dialog.warning({
    title,
    content,
    positiveText,
    negativeText: 'İptal',
    onAfterLeave: () => confirmations.delete(confirmation),
    onPositiveClick: () => {
      confirmations.delete(confirmation)
      if (
        disposed ||
        owner !== userId.value ||
        currentProject !== project.value ||
        revision !== state.revision.value
      )
        return
      action()
    }
  })
  confirmations.add(confirmation)
}
function requestProject(next: MermaidProject) {
  if (!dirty.value) {
    state.replaceProject(next)
    return
  }
  confirmAction(
    'Mevcut proje değiştirilsin mi?',
    'Dosyaya kaydedilmemiş değişiklikleriniz var. Korumak için önce Projeyi kaydet düğmesini kullanın.',
    'Projeyi değiştir',
    () => state.replaceProject(next)
  )
}
function newProject() {
  requestProject(createProject())
}
async function openFile(file?: File) {
  if (file) {
    const owner = userId.value,
      revision = state.revision.value
    try {
      const next = await state.readFile(file)
      if (!disposed && owner === userId.value && revision === state.revision.value)
        requestProject(next)
    } catch (error) {
      if (!disposed) report(error)
    }
  }
}
function chooseFile(event: Event) {
  const target = event.target as HTMLInputElement
  void openFile(target.files?.[0])
  target.value = ''
}
function dropFile(event: DragEvent) {
  void openFile(event.dataTransfer?.files[0])
}
function saveProject() {
  try {
    saveBlobAsFile(
      new Blob([serializeProject(project.value)], { type: 'application/json;charset=utf-8' }),
      safeName(project.value.name) + '.mmdproj'
    )
    state.markDownloaded()
    message.success('Proje dosyasının indirmesi başlatıldı.')
  } catch (error) {
    report(error)
  }
}
async function copyCode() {
  try {
    await navigator.clipboard.writeText(active.value.code)
    message.success('Kod panoya kopyalandı.')
  } catch {
    message.warning('Panoya erişilemedi. Editörde Ctrl/Cmd+A ve Ctrl/Cmd+C kullanabilirsiniz.')
  }
}
async function exportDiagram() {
  if (exporting.value || !preview.value) return
  exporting.value = true
  const title = active.value.title,
    format = exportFormat.value,
    owner = userId.value
  try {
    const blob = await preview.value.requestExport(format, exportScale.value, transparent.value)
    if (disposed || owner !== userId.value) return
    saveBlobAsFile(blob, safeName(title) + '.' + format)
    exportVisible.value = false
    message.success('Görsel dosyasının indirmesi başlatıldı.')
  } catch (error) {
    if (!disposed && owner === userId.value) report(error)
  } finally {
    exporting.value = false
  }
}
let resizing = false
function startResize(event: PointerEvent) {
  resizing = true
  ;(event.currentTarget as HTMLElement).setPointerCapture(event.pointerId)
  event.preventDefault()
}
function resizePointer(event: PointerEvent) {
  if (!resizing || !workspace.value) return
  const bounds = workspace.value.getBoundingClientRect()
  editorWidth.value = Math.max(
    25,
    Math.min(65, ((event.clientX - bounds.left) / bounds.width) * 100)
  )
}
function stopResize() {
  resizing = false
}
function resizeKeyboard(event: KeyboardEvent) {
  if (!['ArrowLeft', 'ArrowRight'].includes(event.key)) return
  event.preventDefault()
  editorWidth.value = Math.max(
    25,
    Math.min(65, editorWidth.value + (event.key === 'ArrowRight' ? 2 : -2))
  )
}
function shortcut(event: KeyboardEvent) {
  if (helpVisible.value || templatesVisible.value || exportVisible.value) return
  if (event.key === 'F2') {
    event.preventDefault()
    titleInput.value?.focus()
    return
  }
  if (!event.ctrlKey && !event.metaKey) return
  if (event.key.toLowerCase() === 's') {
    event.preventDefault()
    saveProject()
  }
  if (event.key === 'Enter') {
    event.preventDefault()
    preview.value?.render()
  }
}
window.addEventListener('keydown', shortcut)
onBeforeUnmount(() => {
  disposed = true
  cancelConfirmations()
  window.removeEventListener('keydown', shortcut)
})
</script>

<style scoped>
.mermaid-workshop {
  min-width: 0;
}
.project-name {
  flex: 1;
  min-width: 200px;
  max-width: 500px;
}
.project-name :deep(.n-input) {
  flex: 1;
  min-width: 120px;
}
.toolbar,
.diagram-toolbar {
  margin-block: 16px;
}
.diagram-title {
  width: min(100%, 250px);
}
.diagram-tabs {
  display: flex;
  gap: 8px;
  flex: 1;
  min-width: 0;
  overflow-x: auto;
  padding-block: 4px;
}
.diagram-tab {
  display: flex;
  align-items: center;
  gap: 2px;
  flex-shrink: 0;
}
.theme-select {
  width: 130px;
}
.workspace {
  display: grid;
  grid-template-columns: minmax(0, var(--editor-width)) 10px minmax(0, 1fr);
  min-height: 520px;
}
.resizer {
  cursor: col-resize;
  touch-action: none;
  border-radius: 4px;
}
.resizer:hover,
.resizer:focus-visible {
  background: v-bind('themeVars.primaryColor');
}
.resizer:focus-visible {
  outline: 2px solid v-bind('themeVars.primaryColor');
  outline-offset: 2px;
}
.storage-warning,
.render-error {
  margin-block: 12px;
}
.render-error pre {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  margin: 0 0 8px;
}
.workspace-footer {
  padding-top: 12px;
  font-size: 12px;
}
.template-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(220px, 100%), 1fr));
  gap: 12px;
  margin-top: 16px;
}
.template-button {
  height: auto;
  min-height: 80px;
  white-space: normal;
  text-align: left;
  padding: 14px;
}
.template-button span,
.template-button strong,
.template-button small {
  display: block;
}
.template-button small {
  margin-top: 6px;
  font-weight: normal;
  color: v-bind('themeVars.textColor2');
  line-height: 1.5;
}
.licenses {
  max-height: 300px;
  overflow: auto;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  font-size: 12px;
}
@media (max-width: 1000px) {
  .workspace {
    grid-template-columns: minmax(0, 1fr);
    gap: 12px;
  }
  .resizer {
    display: none;
  }
}
@media (max-width: 600px) {
  .mermaid-workshop :deep(.n-card__content) {
    padding: 12px;
  }
  .mermaid-workshop :deep(.n-button) {
    min-height: 44px;
  }
}
</style>
<style>
.workshop-dialog {
  width: min(700px, calc(100vw - 32px));
  max-height: calc(100dvh - 48px);
  overflow: auto;
}
</style>
