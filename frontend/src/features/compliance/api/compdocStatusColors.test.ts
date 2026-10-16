import { expect, it } from 'vitest'
import { lightTheme, darkTheme } from 'naive-ui'
import { statusColors } from './compdocCatalog'
import { accessibleTagColors, statusTagColors } from './compdocStatusColors'

for (const theme of [lightTheme, darkTheme]) {
  it(`keeps every semantic status readable on the ${theme.name} provider surface`, () => {
    for (const status of Object.keys(statusColors)) {
      const colors = statusTagColors(status, theme.common!.cardColor!)!
      expect(colors).toBeDefined()
      expect(ratio(colors.color, colors.textColor), status).toBeGreaterThanOrEqual(4.5)
    }
  })
}

it('uses native theme styling for unrecognized statuses or unsupported surfaces', () => {
  expect(statusTagColors('custom', '#fff')).toBeUndefined()
  expect(accessibleTagColors('#c2410c', 'var(--surface)')).toBeUndefined()
})

function ratio(first: string, second: string) {
  function luminance(hex: string) {
    const channels = [1, 3, 5].map((offset) => parseInt(hex.slice(offset, offset + 2), 16) / 255)
    const linear = channels.map((value) =>
      value > 0.04045 ? Math.pow((value + 0.055) / 1.055, 2.4) : value / 12.92
    )
    return linear[0] * 0.2126 + linear[1] * 0.7152 + linear[2] * 0.0722
  }
  const values = [luminance(first), luminance(second)].sort((left, right) => right - left)
  return (values[0] + 0.05) / (values[1] + 0.05)
}
