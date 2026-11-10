export function normalizedSource(value: string): string {
  const text = value.replace(/^\uFEFF/, '').replace(/\r\n?/g, '\n')
  const lines = text.split('\n')
  for (let start = 0; start < lines.length; start++) {
    const opening = lines[start].match(/^[ \t]*(`{3,}|~{3,})[ \t]*mermaid(?:[ \t].*)?$/i)
    if (!opening) continue
    const close = new RegExp('^[ \\t]*' + opening[1][0] + '{' + opening[1].length + ',}[ \\t]*$')
    for (let end = start + 1; end < lines.length; end++)
      if (close.test(lines[end]))
        return lines
          .slice(start + 1, end)
          .join('\n')
          .trim()
  }
  return text.trim()
}
export function safeName(value: string): string {
  return (
    value
      .trim()
      .replace(/[\\/:*?"<>|\u0000-\u001f]/g, '-')
      .replace(/[. ]+$/g, '')
      .replace(/\.(mmdproj|json|svg|png)$/i, '') || 'diyagram'
  ).slice(0, 90)
}
const escapeHtml = (value: string) =>
  value.replace(
    /[&<>"']/g,
    (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[char]!
  )
/** Every source fragment is escaped before the editor's decorative highlight overlay. */
export function highlightedSource(text: string): string {
  const pattern =
    /%%[^\n]*|"(?:\\.|[^"\\])*"|(?:--?>+|==>+|-\.->|<\|--|\|\|--o\{|--\|>)[^\S\n]*|\b(?:flowchart|graph|sequenceDiagram|classDiagram|erDiagram|stateDiagram-v2|gantt|pie|mindmap|gitGraph|timeline|subgraph|end|direction|autonumber|actor|participant|alt|else|opt|loop|par|and|rect|note|Note|title|section|dateFormat|axisFormat|excludes|class|state|commit|branch|checkout|merge|LR|RL|TD|TB|BT)\b/g
  let result = '',
    cursor = 0
  for (const match of text.matchAll(pattern)) {
    const token = match[0],
      kind = token.startsWith('%%')
        ? 'comment'
        : token.startsWith('"')
          ? 'string'
          : /^[<>=|.-]/.test(token)
            ? 'arrow'
            : 'keyword'
    result +=
      escapeHtml(text.slice(cursor, match.index)) +
      `<span class="syntax-${kind}">${escapeHtml(token)}</span>`
    cursor = match.index! + token.length
  }
  return result + escapeHtml(text.slice(cursor)) + '\n'
}
