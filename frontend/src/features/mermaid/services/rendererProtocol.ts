export type RendererMessage =
  | { channel: string; type: 'ready' }
  | { channel: string; type: 'rendered'; revision: number; width: number; height: number }
  | { channel: string; type: 'error'; revision: number; message: string; line: number }
  | { channel: string; type: 'viewport'; scale: number }
  | {
      channel: string
      type: 'exported'
      revision: number
      requestId: string
      bytes: ArrayBuffer
      format: 'svg' | 'png'
    }
  | { channel: string; type: 'export-error'; revision: number; requestId: string; message: string }

const finite = (value: unknown): value is number =>
  typeof value === 'number' && Number.isFinite(value)
export function isRendererMessage(
  event: Pick<MessageEvent, 'source' | 'data'>,
  frame: Window | null,
  channel: string
): event is MessageEvent<RendererMessage> {
  if (!frame || event.source !== frame || !event.data || event.data.channel !== channel)
    return false
  const data = event.data
  if (data.type === 'ready') return true
  if (data.type === 'viewport') return finite(data.scale) && data.scale > 0 && data.scale <= 8
  if (!Number.isSafeInteger(data.revision) || data.revision < 0) return false
  if (data.type === 'rendered')
    return finite(data.width) && finite(data.height) && data.width > 0 && data.height > 0
  if (data.type === 'error')
    return (
      typeof data.message === 'string' &&
      data.message.length <= 3500 &&
      Number.isSafeInteger(data.line)
    )
  if (data.type === 'export-error')
    return typeof data.message === 'string' && typeof data.requestId === 'string'
  return (
    data.type === 'exported' &&
    typeof data.requestId === 'string' &&
    ['svg', 'png'].includes(data.format) &&
    data.bytes instanceof ArrayBuffer &&
    data.bytes.byteLength <= 128 * 1024 * 1024
  )
}
const escapeAttribute = (text: string) =>
  text.replace(
    /[&"<>]/g,
    (value) => ({ '&': '&amp;', '"': '&quot;', '<': '&lt;', '>': '&gt;' })[value]!
  )

/** Opaque-origin frame: only this classic bundle may run; diagram resources cannot leave it. */
export function createRendererDocument(
  bundleUrl: string,
  channel: string,
  parentOrigin: string
): string {
  const url = new URL(bundleUrl, parentOrigin)
  if (
    url.origin !== parentOrigin ||
    !['https:', 'http:'].includes(url.protocol) ||
    !/^[a-zA-Z0-9_-]+$/.test(channel)
  )
    throw new Error('Geçersiz çizim motoru adresi.')
  const policy = `default-src 'none'; script-src ${url.href}; style-src 'unsafe-inline'; img-src data: blob:; font-src data:; connect-src 'none'; worker-src 'none'; base-uri 'none'; form-action 'none'`
  return `<!doctype html><html lang="tr"><head><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="${escapeAttribute(policy)}"><style>html,body{margin:0;width:100%;height:100%;overflow:hidden}#viewport{position:absolute;inset:0;overflow:hidden;touch-action:none;cursor:grab;outline-offset:-3px}#diagram{position:absolute;transform-origin:0 0}#host{position:absolute;left:-100000px;top:0;visibility:hidden}svg{max-width:none!important}</style></head><body><div id="viewport" tabindex="0" aria-label="Diyagram: ok tuşlarıyla taşıyın, artı ve eksi ile yakınlaştırın."><div id="diagram"></div></div><div id="host" aria-hidden="true"></div><script src="${escapeAttribute(url.href)}" data-channel="${escapeAttribute(channel)}" data-parent-origin="${escapeAttribute(parentOrigin)}"></script></body></html>`
}
