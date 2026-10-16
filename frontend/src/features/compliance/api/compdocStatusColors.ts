import { statusColors } from './compdocCatalog'

type Rgb = [number, number, number]

/** Resolve semantic tags on the provider's surface without translucent contrast surprises. */
export function statusTagColors(status: string, surface: string) {
  const color = statusColors[status]?.color
  return color ? accessibleTagColors(color, surface) : undefined
}

/** Keep the semantic hue and adjust its brightness until text contrast reaches 4.5:1. */
export function accessibleTagColors(color: string, surface: string) {
  const base = parseRgb(color)
  const backing = parseRgb(surface)
  if (!base || !backing) return undefined
  const background = mix(backing, base, 0.16)
  const black: Rgb = [0, 0, 0]
  const white: Rgb = [255, 255, 255]
  const endpoint = contrast(black, background) > contrast(white, background) ? black : white
  let foreground = base
  for (let step = 1; contrast(foreground, background) < 4.5 && step <= 100; step++) {
    foreground = mix(base, endpoint, step / 100)
  }
  return { color: hex(background), textColor: hex(foreground) }
}

function parseRgb(value: string): Rgb | null {
  if (typeof value !== 'string') return null
  const hexValue = /^#([\da-f]{3}|[\da-f]{6})$/i.exec(value)?.[1]
  if (hexValue) {
    const expanded =
      hexValue.length === 3 ? [...hexValue].map((digit) => digit + digit).join('') : hexValue
    return [0, 2, 4].map((index) => parseInt(expanded.slice(index, index + 2), 16)) as Rgb
  }
  const rgb = /^rgb\(\s*([\d.]+),\s*([\d.]+),\s*([\d.]+)\s*\)$/i.exec(value)
  if (!rgb) return null
  const channels = rgb.slice(1).map(Number)
  return channels.every((channel) => Number.isFinite(channel) && channel >= 0 && channel <= 255)
    ? (channels as Rgb)
    : null
}

function mix(left: Rgb, right: Rgb, amount: number): Rgb {
  return left.map((channel, index) =>
    Math.round(channel + (right[index] - channel) * amount)
  ) as Rgb
}

function luminance(rgb: Rgb) {
  const [red, green, blue] = rgb.map((channel) => {
    const normalized = channel / 255
    return normalized <= 0.04045 ? normalized / 12.92 : ((normalized + 0.055) / 1.055) ** 2.4
  })
  return red * 0.2126 + green * 0.7152 + blue * 0.0722
}

function contrast(left: Rgb, right: Rgb) {
  const first = luminance(left)
  const second = luminance(right)
  return (Math.max(first, second) + 0.05) / (Math.min(first, second) + 0.05)
}

function hex(rgb: Rgb) {
  return '#' + rgb.map((channel) => channel.toString(16).padStart(2, '0')).join('')
}
