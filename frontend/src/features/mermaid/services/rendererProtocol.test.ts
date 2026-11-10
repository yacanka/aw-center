import { describe, expect, it } from 'vitest'
import { createRendererDocument, isRendererMessage } from './rendererProtocol'

describe('isolated Mermaid renderer boundary', () => {
  it('accepts only messages from the expected frame and channel', () => {
    const frame = {} as Window
    const data = {
      channel: 'frame-channel',
      type: 'rendered',
      revision: 4,
      width: 200,
      height: 100
    }
    expect(isRendererMessage({ source: frame, data }, frame, 'frame-channel')).toBe(true)
    expect(isRendererMessage({ source: {} as Window, data }, frame, 'frame-channel')).toBe(false)
    expect(
      isRendererMessage(
        { source: frame, data: { ...data, channel: 'other' } },
        frame,
        'frame-channel'
      )
    ).toBe(false)
    expect(
      isRendererMessage({ source: frame, data: { ...data, revision: '4' } }, frame, 'frame-channel')
    ).toBe(false)
    expect(
      isRendererMessage(
        { source: frame, data: { ...data, type: 'unknown' } },
        frame,
        'frame-channel'
      )
    ).toBe(false)
  })
  it('allows only the exact trusted bundle while forbidding remote data and form traffic', () => {
    const document = createRendererDocument(
      'https://aw.example/core/assets/renderer-123.js',
      'safe-channel',
      'https://aw.example'
    )
    expect(document).toContain("default-src 'none'")
    expect(document).toContain("connect-src 'none'")
    expect(document).toContain("form-action 'none'")
    expect(document).not.toContain("'unsafe-eval'")
    expect(document).not.toContain("script-src 'self'")
    expect(document).toContain('https://aw.example/core/assets/renderer-123.js')
    expect(() =>
      createRendererDocument('https://external.example/a.js', 'channel', 'https://aw.example')
    ).toThrow()
  })
})
