import mermaid from 'mermaid'
import { MAX_SOURCE, THEMES, type DiagramTheme } from '../models/project'
import { normalizedSource } from '../services/sourceText'
import { validateSvg } from './svgSecurity'
import { backgrounds, themeConfig } from './theme'

const script = document.currentScript as HTMLScriptElement
const channel = script.dataset.channel!,
  parentOrigin = script.dataset.parentOrigin!
const viewport = document.getElementById('viewport')!,
  diagram = document.getElementById('diagram')!,
  host = document.getElementById('host')!
let revision = 0,
  validRevision = -1,
  renderId = 0,
  width = 0,
  height = 0,
  scale = 1,
  panX = 0,
  panY = 0
let svg: SVGSVGElement | null = null,
  theme: DiagramTheme = 'studio'
let queue = Promise.resolve()
const send = (data: object, transfer: Transferable[] = []) =>
  parent.postMessage({ channel, ...data }, parentOrigin, transfer)
function transform() {
  diagram.style.transform = `translate(${panX}px,${panY}px) scale(${scale})`
  send({ type: 'viewport', scale })
}
function fit() {
  if (!svg || !viewport.clientWidth || !viewport.clientHeight) return
  scale = Math.max(
    0.02,
    Math.min(1.25, (viewport.clientWidth - 50) / width, (viewport.clientHeight - 50) / height)
  )
  panX = (viewport.clientWidth - width * scale) / 2
  panY = (viewport.clientHeight - height * scale) / 2
  transform()
}
function zoom(next: number, x = viewport.clientWidth / 2, y = viewport.clientHeight / 2) {
  if (!svg) return
  const previous = scale
  scale = Math.max(0.02, Math.min(8, next))
  panX = x - ((x - panX) * scale) / previous
  panY = y - ((y - panY) * scale) / previous
  transform()
}
async function render(code: string, nextTheme: DiagramTheme, current: number) {
  if (current !== revision) return
  try {
    if (code.length > MAX_SOURCE)
      throw new Error('Şema kaynak kodu en fazla 120.000 karakter olabilir.')
    mermaid.initialize(themeConfig(nextTheme))
    const result = await mermaid.render(`awMermaid${++renderId}`, normalizedSource(code), host)
    if (current !== revision) return
    const output = document.importNode(validateSvg(result.svg), true)
    diagram.replaceChildren(output)
    const viewBox = output
      .getAttribute('viewBox')
      ?.trim()
      .split(/[\s,]+/)
      .map(Number)
    width = viewBox?.length === 4 ? viewBox[2] : 0
    height = viewBox?.length === 4 ? viewBox[3] : 0
    if (!(width > 0 && height > 0 && Number.isFinite(width) && Number.isFinite(height)))
      throw new Error('Diyagram boyutları hesaplanamadı.')
    output.setAttribute('width', String(width))
    output.setAttribute('height', String(height))
    output.setAttribute('role', 'img')
    output.setAttribute('aria-label', 'Mermaid diyagramı')
    svg = output
    theme = nextTheme
    validRevision = current
    document.body.style.background = backgrounds[theme]
    fit()
    send({ type: 'rendered', revision: current, width, height })
  } catch (error) {
    if (current !== revision) return
    const message = String(error instanceof Error ? error.message : error)
      .replace(/<[^>]*>/g, '')
      .slice(0, 3500)
    const line = Number(message.match(/(?:line|satır)\s*(\d+)/i)?.[1] || 0)
    send({ type: 'error', revision: current, message, line })
  } finally {
    host.replaceChildren()
  }
}
function serializedSvg(transparent: boolean): string {
  const copy = svg!.cloneNode(true) as SVGSVGElement
  copy.setAttribute('xmlns', 'http://www.w3.org/2000/svg')
  copy.setAttribute('width', String(Math.ceil(width)))
  copy.setAttribute('height', String(Math.ceil(height)))
  copy.style.background = 'transparent'
  if (!transparent) {
    const box = copy
      .getAttribute('viewBox')!
      .split(/[\s,]+/)
      .map(Number)
    const background = document.createElementNS('http://www.w3.org/2000/svg', 'rect')
    for (const [name, value] of Object.entries({
      x: box[0],
      y: box[1],
      width: box[2],
      height: box[3],
      fill: backgrounds[theme]
    }))
      background.setAttribute(name, String(value))
    copy.insertBefore(background, copy.firstChild)
  }
  const source = new XMLSerializer().serializeToString(copy)
  validateSvg(source)
  return '<?xml version="1.0" encoding="UTF-8"?>\n' + source
}
async function exportDiagram(data: {
  revision: number
  requestId: string
  format: 'svg' | 'png'
  factor: number
  transparent: boolean
}) {
  let url: string | undefined
  try {
    if (!svg || data.revision !== revision || validRevision !== revision)
      throw new Error('Önce güncel kodu başarıyla çizin.')
    const source = serializedSvg(data.transparent)
    let blob = new Blob([source], { type: 'image/svg+xml;charset=utf-8' })
    if (data.format === 'png') {
      const w = Math.ceil(width * data.factor),
        h = Math.ceil(height * data.factor)
      if (w > 16384 || h > 16384 || w * h > 32000000)
        throw new Error('PNG çok büyük. Daha düşük çözünürlük seçin veya SVG kullanın.')
      const image = new Image()
      url = URL.createObjectURL(blob)
      await new Promise<void>((resolve, reject) => {
        image.onload = () => resolve()
        image.onerror = () => reject(new Error('PNG oluşturulamadı. SVG biçimini deneyin.'))
        image.src = url!
      })
      const canvas = document.createElement('canvas')
      canvas.width = w
      canvas.height = h
      const context = canvas.getContext('2d')
      if (!context) throw new Error('Tarayıcı PNG dönüşümünü desteklemiyor.')
      context.drawImage(image, 0, 0, w, h)
      blob = await new Promise<Blob>((resolve, reject) =>
        canvas.toBlob(
          (value) => (value ? resolve(value) : reject(new Error('PNG oluşturulamadı.'))),
          'image/png'
        )
      )
    }
    if (data.revision !== revision)
      throw new Error('Dışa aktarım sırasında şema değişti. Yeniden deneyin.')
    const bytes = await blob.arrayBuffer()
    send(
      {
        type: 'exported',
        revision: data.revision,
        requestId: data.requestId,
        format: data.format,
        bytes
      },
      [bytes]
    )
  } catch (error) {
    send({
      type: 'export-error',
      revision: data.revision,
      requestId: data.requestId,
      message: error instanceof Error ? error.message : 'Görsel oluşturulamadı.'
    })
  } finally {
    if (url) URL.revokeObjectURL(url)
  }
}
window.addEventListener('message', (event) => {
  const data = event.data
  if (event.source !== parent || event.origin !== parentOrigin || !data || data.channel !== channel)
    return
  if (
    data.type === 'render' &&
    Number.isSafeInteger(data.revision) &&
    data.revision >= revision &&
    typeof data.code === 'string' &&
    THEMES.includes(data.theme)
  ) {
    revision = data.revision
    validRevision = -1
    queue = queue.then(() => render(data.code, data.theme, data.revision))
  } else if (
    data.type === 'invalidate' &&
    Number.isSafeInteger(data.revision) &&
    data.revision >= revision
  ) {
    revision = data.revision
    validRevision = -1
    if (data.clear) {
      svg = null
      diagram.replaceChildren()
    }
  } else if (data.type === 'view') {
    if (data.action === 'fit') fit()
    if (data.action === 'in') zoom(scale * 1.2)
    if (data.action === 'out') zoom(scale / 1.2)
    if (data.action === 'actual') zoom(1)
  } else if (
    data.type === 'export' &&
    typeof data.requestId === 'string' &&
    Number.isSafeInteger(data.revision) &&
    ['svg', 'png'].includes(data.format) &&
    [1, 2, 3].includes(data.factor) &&
    typeof data.transparent === 'boolean'
  )
    void exportDiagram(data)
})
let pointer: { id: number; x: number; y: number; panX: number; panY: number } | null = null
viewport.addEventListener('pointerdown', (event) => {
  if (event.button !== 0 || !svg) return
  pointer = { id: event.pointerId, x: event.clientX, y: event.clientY, panX, panY }
  viewport.setPointerCapture(event.pointerId)
})
viewport.addEventListener('pointermove', (event) => {
  if (pointer?.id !== event.pointerId) return
  panX = pointer.panX + event.clientX - pointer.x
  panY = pointer.panY + event.clientY - pointer.y
  transform()
})
for (const name of ['pointerup', 'pointercancel', 'lostpointercapture'])
  viewport.addEventListener(name, () => {
    pointer = null
  })
viewport.addEventListener(
  'wheel',
  (event) => {
    if (!svg) return
    event.preventDefault()
    if (event.ctrlKey || event.metaKey)
      zoom(scale * Math.exp(-event.deltaY * 0.002), event.clientX, event.clientY)
    else {
      panX -= event.deltaX
      panY -= event.deltaY
      transform()
    }
  },
  { passive: false }
)
viewport.addEventListener('dblclick', fit)
viewport.addEventListener('keydown', (event) => {
  if (!['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown', '+', '=', '-', '0'].includes(event.key))
    return
  event.preventDefault()
  if (event.key === '+' || event.key === '=') zoom(scale * 1.2)
  else if (event.key === '-') zoom(scale / 1.2)
  else if (event.key === '0') fit()
  else {
    panX += event.key === 'ArrowLeft' ? 30 : event.key === 'ArrowRight' ? -30 : 0
    panY += event.key === 'ArrowUp' ? 30 : event.key === 'ArrowDown' ? -30 : 0
    transform()
  }
})
new ResizeObserver(fit).observe(viewport)
send({ type: 'ready' })
