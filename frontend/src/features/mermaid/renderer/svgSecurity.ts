/** Validate before mounting or exporting. CSP is also enforced while Mermaid draws. */
export function validateSvg(source: string): SVGSVGElement {
  const document = new DOMParser().parseFromString(source, 'image/svg+xml')
  const root = document.documentElement
  if (root.localName !== 'svg' || document.querySelector('parsererror'))
    throw new Error('Geçerli SVG oluşturulamadı.')
  for (const element of [root, ...Array.from(root.querySelectorAll('*'))]) {
    if (
      [
        'script',
        'foreignobject',
        'iframe',
        'object',
        'embed',
        'a',
        'animate',
        'set',
        'animatetransform',
        'animatemotion'
      ].includes(element.localName.toLowerCase())
    )
      throw new Error('Diyagram etkin veya desteklenmeyen içerik barındırıyor.')
    for (const attribute of Array.from(element.attributes)) {
      if (/^on/i.test(attribute.name)) throw new Error('Diyagram etkin içerik barındırıyor.')
      if (
        ['href', 'src'].includes(attribute.localName) &&
        !/^(?:#[A-Za-z0-9_.:-]+|data:image\/(?:png|jpeg|gif|webp);base64,[A-Za-z0-9+/=\s]+)$/.test(
          attribute.value
        )
      )
        throw new Error('Haricî görseller ve bağlantılar desteklenmiyor.')
      if (attribute.localName === 'style' || /url\s*\(/i.test(attribute.value))
        validateCss(attribute.value)
    }
    if (element.localName === 'style') validateCss(element.textContent || '')
  }
  return root as unknown as SVGSVGElement
}
function validateCss(css: string): void {
  // Reject CSS escapes as well: otherwise escaped url/@import can evade URI checks.
  const withoutLocalMarkers = css.replace(/url\(\s*["']?#[A-Za-z0-9_.:-]+["']?\s*\)/gi, '')
  if (/[\\]|@import|@font-face|url\s*\(|expression\s*\(/i.test(withoutLocalMarkers))
    throw new Error('Haricî veya desteklenmeyen diyagram stili.')
}
