import { computed, onScopeDispose, ref, watch, type Ref } from 'vue'
import {
  createDiagram,
  createProject,
  MAX_DIAGRAMS,
  MAX_IMPORT_BYTES,
  MAX_SOURCE,
  MAX_TOTAL_SOURCE,
  normalizeLabel,
  parseProject,
  validateProject,
  type DiagramTheme,
  type MermaidProject
} from '../models/project'
import { INITIAL } from '../models/templates'

interface Draft {
  project: MermaidProject
  dirty: boolean
  live: boolean
  editorWidth: number
}
interface History {
  entries: string[]
  index: number
}
const keyFor = (userId: number) => `aw-center:mermaid:v1:${userId}`

/** One local project per account. Capture ownership before scheduling any write. */
export function useMermaidProject(userId: Ref<number | undefined>) {
  const project = ref(
    createProject('Yeni proje', [createDiagram({ title: 'Akış şeması', code: INITIAL })])
  )
  const dirty = ref(false),
    live = ref(true),
    editorWidth = ref(40),
    storageError = ref('')
  const revision = ref(0)
  const histories = new Map<string, History>()
  let owner: number | undefined, saveTimer: ReturnType<typeof setTimeout> | undefined
  let disposed = false
  const active = computed(() =>
    project.value.diagrams.find((item) => item.id === project.value.activeDiagramId)!
  )
  const canUndo = computed(() => {
    revision.value
    return history().index > 0
  })
  const canRedo = computed(() => {
    revision.value
    const item = history()
    return item.index < item.entries.length - 1
  })

  function history(): History {
    let item = histories.get(active.value.id)
    if (!item) {
      item = { entries: [active.value.code], index: 0 }
      histories.set(active.value.id, item)
    }
    return item
  }
  function flush() {
    clearTimeout(saveTimer)
    if (!owner) return
    try {
      const snapshot: Draft = {
        project: validateProject(project.value),
        dirty: dirty.value,
        live: live.value,
        editorWidth: editorWidth.value
      }
      localStorage.setItem(keyFor(owner), JSON.stringify(snapshot))
      storageError.value = ''
    } catch {
      storageError.value = 'Otomatik saklama yapılamadı. Projeyi kaydet ile dosya indirin.'
    }
  }
  function scheduleSave() {
    clearTimeout(saveTimer)
    saveTimer = setTimeout(flush, 450)
  }
  function changed(content = true) {
    if (content) dirty.value = true
    revision.value++
    scheduleSave()
  }
  function replaceProject(next: MermaidProject, modified = false) {
    project.value = validateProject(next)
    dirty.value = modified
    histories.clear()
    revision.value++
    scheduleSave()
  }
  function editCode(code: string, record = true) {
    if (code.length > MAX_SOURCE)
      throw new Error('Şema kaynak kodu en fazla 120.000 karakter olabilir.')
    const total = project.value.diagrams.reduce(
      (sum, item) => sum + (item.id === active.value.id ? code.length : item.code.length),
      0
    )
    if (total > MAX_TOTAL_SOURCE)
      throw new Error('Toplam kaynak kodu en fazla 4.000.000 karakter olabilir.')
    if (code === active.value.code) return
    const item = history()
    active.value.code = code
    if (record) {
      item.entries = item.entries.slice(0, item.index + 1)
      item.entries.push(code)
      if (item.entries.length > 60) item.entries.shift()
      item.index = item.entries.length - 1
    }
    changed()
  }
  function moveHistory(delta: number) {
    const item = history(),
      next = item.index + delta
    if (next < 0 || next >= item.entries.length) return
    editCode(item.entries[next], false)
    item.index = next
    revision.value++
  }
  function selectDiagram(id: string) {
    if (!project.value.diagrams.some((item) => item.id === id)) return
    history()
    project.value.activeDiagramId = id
    changed(false)
  }
  function addDiagram(code = '', title?: string) {
    if (project.value.diagrams.length >= MAX_DIAGRAMS)
      throw new Error('Bir projede en fazla 200 şema olabilir.')
    let index = 1
    while (project.value.diagrams.some((item) => item.title === `Şema ${index}`)) index++
    const item = createDiagram({ code, title: title || `Şema ${index}` })
    validateProject({ ...project.value, diagrams: [...project.value.diagrams, item] })
    history()
    project.value.diagrams.push(item)
    project.value.activeDiagramId = item.id
    changed()
  }
  function removeDiagram(id: string) {
    const index = project.value.diagrams.findIndex((item) => item.id === id)
    if (index < 0) return
    project.value.diagrams.splice(index, 1)
    histories.delete(id)
    if (!project.value.diagrams.length) project.value.diagrams.push(createDiagram())
    if (project.value.activeDiagramId === id)
      project.value.activeDiagramId =
        project.value.diagrams[Math.min(index, project.value.diagrams.length - 1)].id
    changed()
  }
  async function readFile(file: File): Promise<MermaidProject> {
    if (file.size > MAX_IMPORT_BYTES) throw new Error('Proje dosyası 16 MiB sınırını aşıyor.')
    if (!/\.(mmdproj|json)$/i.test(file.name))
      throw new Error('Lütfen .mmdproj veya .json proje dosyası seçin.')
    const before = revision.value
    const result = parseProject(await file.text())
    if (disposed || before !== revision.value)
      throw new Error('Dosya okunurken proje değişti. Dosyayı yeniden açın.')
    return result
  }
  function restore(nextOwner: number | undefined) {
    if (owner) flush()
    owner = nextOwner
    histories.clear()
    storageError.value = ''
    project.value = createProject('Yeni proje', [
      createDiagram({ title: 'Akış şeması', code: INITIAL })
    ])
    dirty.value = false
    live.value = true
    editorWidth.value = 40
    if (owner) {
      try {
        const raw = localStorage.getItem(keyFor(owner))
        if (raw) {
          const draft = JSON.parse(raw) as Draft
          project.value = validateProject(draft.project)
          dirty.value = draft.dirty !== false
          live.value = draft.live !== false
          if (Number.isFinite(draft.editorWidth))
            editorWidth.value = Math.max(25, Math.min(65, draft.editorWidth))
        }
      } catch {
        storageError.value =
          'Yerel taslak okunamadı. Proje dosyanızı açabilir veya yeni projeyle devam edebilirsiniz.'
      }
    }
    revision.value++
  }
  watch(userId, restore, { immediate: true, flush: 'sync' })
  watch([live, editorWidth], scheduleSave, { flush: 'sync' })
  const onPageHide = () => flush()
  window.addEventListener('pagehide', onPageHide)
  onScopeDispose(() => {
    disposed = true
    flush()
    window.removeEventListener('pagehide', onPageHide)
  })
  return {
    project,
    active,
    dirty,
    live,
    editorWidth,
    storageError,
    revision,
    canUndo,
    canRedo,
    editCode,
    undo: () => moveHistory(-1),
    redo: () => moveHistory(1),
    selectDiagram,
    addDiagram,
    removeDiagram,
    replaceProject,
    readFile,
    flush,
    renameProject: (name: string) => {
      project.value.name = normalizeLabel(name, 'Yeni proje')
      changed()
    },
    renameDiagram: (title: string) => {
      active.value.title = normalizeLabel(title, 'Adsız şema')
      changed()
    },
    setTheme: (theme: DiagramTheme) => {
      active.value.theme = theme
      changed()
    },
    markDownloaded: () => {
      dirty.value = false
      scheduleSave()
    }
  }
}
