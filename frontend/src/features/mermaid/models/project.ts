/** Portable v1 contract shared with the standalone Mermaid Atölyesi editor. */
export const FORMAT = 'mermaid-atolyesi-project'
export const THEMES = ['studio', 'default', 'forest', 'dark', 'neutral'] as const
export type DiagramTheme = (typeof THEMES)[number]
export interface MermaidDiagram {
  id: string
  title: string
  code: string
  theme: DiagramTheme
}
export interface MermaidProject {
  format: typeof FORMAT
  version: 1
  name: string
  activeDiagramId: string
  diagrams: MermaidDiagram[]
}
export const MAX_SOURCE = 120000
export const MAX_DIAGRAMS = 200
export const MAX_TOTAL_SOURCE = 4000000
export const MAX_IMPORT_BYTES = 16 * 1024 * 1024
const isObject = (value: unknown): value is Record<string, unknown> =>
  value !== null && typeof value === 'object' && !Array.isArray(value)

export function normalizeLabel(value: unknown, fallback: string): string {
  if (value === undefined) return fallback
  if (typeof value !== 'string') throw new Error('Başlık metin olmalıdır.')
  if (/[\u0000-\u001f\u007f-\u009f\u2028\u2029]/.test(value))
    throw new Error('Başlık kontrol karakteri veya satır sonu içeremez.')
  return Array.from(value.trim() || fallback)
    .slice(0, 90)
    .join('')
}
function validateDiagram(value: unknown, index: number): MermaidDiagram {
  if (!isObject(value)) throw new Error('Şema geçerli bir nesne olmalıdır.')
  if (typeof value.id !== 'string' || !/^[A-Za-z0-9_-]{1,100}$/.test(value.id))
    throw new Error('Geçersiz şema kimliği.')
  if (typeof value.code !== 'string') throw new Error('Şema kaynak kodu metin olmalıdır.')
  if (value.code.length > MAX_SOURCE)
    throw new Error('Şema kaynak kodu en fazla 120.000 karakter olabilir.')
  if (!THEMES.includes(value.theme as DiagramTheme)) throw new Error('Geçersiz şema teması.')
  return {
    id: value.id,
    title: normalizeLabel(value.title, `Şema ${index + 1}`),
    code: value.code,
    theme: value.theme as DiagramTheme
  }
}
export function validateProject(value: unknown): MermaidProject {
  if (!isObject(value) || value.format !== FORMAT)
    throw new Error('Bu dosya bir Mermaid Atölyesi projesi değil.')
  if (value.version !== 1) throw new Error('Bu proje dosyasının sürümü desteklenmiyor.')
  if (!Array.isArray(value.diagrams) || !value.diagrams.length)
    throw new Error('Proje en az bir şema içermelidir.')
  if (value.diagrams.length > MAX_DIAGRAMS)
    throw new Error('Bir proje en fazla 200 şema içerebilir.')
  const diagrams = value.diagrams.map(validateDiagram)
  const ids = new Set(diagrams.map((item) => item.id))
  if (ids.size !== diagrams.length)
    throw new Error('Aynı şema kimliği birden fazla kez kullanılmış.')
  if (diagrams.reduce((total, item) => total + item.code.length, 0) > MAX_TOTAL_SOURCE)
    throw new Error('Toplam kaynak kodu en fazla 4.000.000 karakter olabilir.')
  if (typeof value.activeDiagramId !== 'string' || !ids.has(value.activeDiagramId))
    throw new Error('Projenin seçili şema kimliği listede bulunamadı.')
  return {
    format: FORMAT,
    version: 1,
    name: normalizeLabel(value.name, 'Yeni proje'),
    activeDiagramId: value.activeDiagramId,
    diagrams
  }
}
export function createDiagram(options: Partial<Omit<MermaidDiagram, 'id'>> = {}): MermaidDiagram {
  return validateDiagram(
    {
      id: `diagram-${crypto.randomUUID()}`,
      title: 'Şema 1',
      code: '',
      theme: 'studio',
      ...options
    },
    0
  )
}
export function createProject(name = 'Yeni proje', diagrams?: MermaidDiagram[]): MermaidProject {
  const items = diagrams?.length ? diagrams : [createDiagram()]
  return validateProject({
    format: FORMAT,
    version: 1,
    name,
    activeDiagramId: items[0].id,
    diagrams: items
  })
}
export function parseProject(text: string): MermaidProject {
  let value: unknown
  try {
    value = JSON.parse(text.replace(/^\uFEFF/, ''))
  } catch {
    throw new Error('Proje dosyası geçerli JSON içermiyor.')
  }
  return validateProject(value)
}
export function serializeProject(project: MermaidProject): string {
  return JSON.stringify(validateProject(project), null, 2) + '\n'
}
