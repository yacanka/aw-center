import { describe, expect, it } from 'vitest'
import { highlightedSource, normalizedSource, safeName } from './sourceText'

describe('Mermaid text boundaries', () => {
  it('extracts fenced Mermaid without interpreting surrounding prose as code', () => {
    expect(
      normalizedSource('Description\r\n```mermaid\r\nflowchart LR\r\n A --> B\r\n```\r\nTail')
    ).toBe('flowchart LR\n A --> B')
  })
  it('escapes source markup and creates safe portable filenames', () => {
    expect(highlightedSource('<img onerror="alert(1)">')).not.toContain('<img')
    expect(safeName('../a:b.mmdproj')).toBe('..-a-b')
  })
})
