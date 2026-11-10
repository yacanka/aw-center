// @vitest-environment jsdom
import { describe, expect, it } from 'vitest'
import { validateSvg } from './svgSecurity'

describe('downloadable self-contained SVG', () => {
  it('preserves diagram geometry and internal marker references', () => {
    const svg = validateSvg(
      '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 100"><style>.edge{marker-end:url(#arrow)}</style><path d="M0 0L20 20"/></svg>'
    )
    expect(svg.getAttribute('viewBox')).toBe('0 0 200 100')
    expect(svg.querySelector('path')).not.toBeNull()
  })
  it.each([
    '<script>alert(1)</script>',
    '<g onload="alert(1)"/>',
    '<foreignObject/>',
    '<image href="https://external.example/image.png"/>',
    '<a href="javascript:alert(1)">click</a>',
    '<style>@import "https://external.example/a.css";</style>',
    '<style>.a{fill:u\\72l(https://external.example/image)}</style>',
    '<g style="fill:url(https://external.example/a)"/>'
  ])('rejects active or externally referenced output: %s', (content) => {
    expect(() => validateSvg(`<svg xmlns="http://www.w3.org/2000/svg">${content}</svg>`)).toThrow()
  })
})
