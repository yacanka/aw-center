// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import ParticleAnimation from './particleTextAnimation.js'

function setup() {
  vi.stubGlobal(
    'ResizeObserver',
    class {
      observe() {}
      disconnect() {}
    }
  )
  const context = {
    clearRect: vi.fn(),
    drawImage: vi.fn(),
    setTransform: vi.fn(),
    globalAlpha: 1,
    measureText: vi.fn(() => ({ width: 200 })),
    fillText: vi.fn(),
    getImageData: vi.fn((_x, _y, width, height) => ({
      data: new Uint8ClampedArray(width * height * 4).fill(255)
    })),
    beginPath: vi.fn(),
    moveTo: vi.fn(),
    arc: vi.fn(),
    fill: vi.fn(),
    fillStyle: ''
  }
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(context as never)
  vi.spyOn(document, 'hidden', 'get').mockReturnValue(false)
  vi.stubGlobal(
    'requestAnimationFrame',
    vi.fn(() => 1)
  )
  vi.stubGlobal('cancelAnimationFrame', vi.fn())
  const canvas = document.createElement('canvas')
  const heading = document.createElement('span')
  for (const [text, top] of [
    ['AW', 200],
    ['Center', 300]
  ] as const) {
    const line = document.createElement('span')
    line.className = 'particle-line'
    line.textContent = text
    vi.spyOn(line, 'getBoundingClientRect').mockReturnValue({ left: 120, top } as DOMRect)
    heading.appendChild(line)
  }
  vi.spyOn(heading, 'getBoundingClientRect').mockReturnValue({
    width: 440,
    height: 200,
    left: 120,
    top: 200
  } as DOMRect)
  vi.spyOn(canvas, 'getBoundingClientRect').mockImplementation(
    () =>
      ({
        width: window.innerWidth,
        height: window.innerHeight,
        left: 100,
        top: 80
      }) as DOMRect
  )
  const animation = new ParticleAnimation(canvas, ['#00000088'], 'AW Center', heading)
  return { animation, context }
}

afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
  vi.useRealTimers()
})

describe('particle heading animation', () => {
  it('places two text lines at the heading while drawing escaped particles on the full screen', () => {
    const { animation, context } = setup()
    expect(context.fillText.mock.calls.map(([value]) => value)).toEqual(['AW', 'Center'])
    expect(animation.ww).toBe(window.innerWidth)
    expect(animation.wh).toBe(window.innerHeight)
    expect(animation.particles[0].dest.x).toBeGreaterThanOrEqual(18)
    animation.particles[0].x = 700
    animation.particles[0].y = 500
    context.drawImage.mockClear()
    animation.render(17)
    expect(context.drawImage.mock.calls[0][1]).toBeGreaterThan(560)
    animation.destroy()
  })

  it('starts with a readable heading before pointer interaction scatters particles', () => {
    const { animation } = setup()
    const first = animation.particles[0]
    expect(Math.abs(first.x - first.dest.x)).toBeLessThan(10)
    expect(Math.abs(first.y - first.dest.y)).toBeLessThan(10)
    expect(first.vx).toBe(0)
    expect(first.vy).toBe(0)
    first.update({ x: first.x - 20, y: first.y }, 1, 80)
    expect(first.vx).not.toBe(0)
    animation.destroy()
  })

  it('keeps viewport bounds and local pointer coordinates when the heading changes size', () => {
    const { animation } = setup()
    vi.mocked(animation.heading.getBoundingClientRect).mockReturnValue({
      width: 320,
      height: 100,
      left: 100,
      top: 80
    } as DOMRect)
    animation.resize()
    expect(animation.ww).toBe(window.innerWidth)
    expect(animation.wh).toBe(window.innerHeight)
    animation.onMouseMove({ clientX: 150, clientY: 110 })
    expect(animation.mouse).toEqual({ x: 50, y: 30 })
    animation.destroy()
  })

  it('releases the pointer when it leaves the heading', () => {
    const { animation } = setup()
    window.dispatchEvent(new MouseEvent('mousemove', { clientX: 140, clientY: 100 }))
    expect(animation.mouse).toEqual({ x: 40, y: 20 })
    window.dispatchEvent(new MouseEvent('mouseleave'))
    expect(animation.mouse.x).toBeLessThan(0)
    expect(animation.mouse.y).toBeLessThan(0)
    animation.destroy()
  })

  it('scans a cropped mask and caches one sprite while compositing every particle separately', () => {
    const { animation, context } = setup()
    const [, , width, height] = context.getImageData.mock.calls[0]
    expect(width * height).toBeLessThan(window.innerWidth * window.innerHeight)
    expect(animation.amount).toBeGreaterThan(1)
    expect(context.arc).toHaveBeenCalledTimes(1)
    expect(context.drawImage).toHaveBeenCalledTimes(animation.amount)
    const oldSprite = animation.sprites.get('#00000088')
    animation.setColors(['#ffffff88'])
    context.drawImage.mockClear()
    animation.render(17)
    expect(context.fillStyle).toBe('#ffffff88')
    expect(context.drawImage).toHaveBeenCalledTimes(animation.amount)
    expect(context.drawImage.mock.calls[0][0]).not.toBe(oldSprite)
    expect(context.arc).toHaveBeenCalledTimes(2)
    animation.destroy()
  })

  it('keeps drawing individual particles after settling, without drawing visible text', () => {
    const { animation, context } = setup()
    for (const particle of animation.particles) {
      particle.x = particle.dest.x
      particle.y = particle.dest.y
      particle.vx = 0
      particle.vy = 0
    }
    context.drawImage.mockClear()
    context.fillText.mockClear()
    animation.tick(17)
    expect(context.drawImage).toHaveBeenCalledTimes(animation.amount)
    expect(context.fillText).not.toHaveBeenCalled()
    context.drawImage.mockClear()
    animation.particles[0].x += 20
    animation.tick(34)
    expect(context.drawImage).toHaveBeenCalledTimes(animation.amount)
    expect(context.fillText).not.toHaveBeenCalled()
    animation.destroy()
  })

  it('keeps a three-pixel sampling grid and aligns both lines to the heading', () => {
    vi.stubGlobal('innerWidth', 1279)
    vi.stubGlobal('innerHeight', 719)
    const { animation, context } = setup()
    for (const particle of animation.particles) {
      expect(particle.dest.x % 3).toBe(0)
      expect(particle.dest.y % 3).toBe(0)
    }
    const first = animation.particles[0]
    expect(first.dest.x).toBe(18)
    expect(context.fillText).toHaveBeenNthCalledWith(1, 'AW', 2, 0)
    expect(context.fillText).toHaveBeenNthCalledWith(2, 'Center', 2, 100)
    animation.destroy()
  })

  it('uses a bounded Retina backing buffer without increasing the particle count', () => {
    const { animation, context } = setup()
    const count = animation.amount
    vi.stubGlobal('devicePixelRatio', 3)
    animation.resize()
    expect(animation.canvas.width).toBe(window.innerWidth * 2)
    expect(animation.canvas.height).toBe(window.innerHeight * 2)
    expect(context.setTransform).toHaveBeenLastCalledWith(2, 0, 0, 2, 0, 0)
    expect(animation.amount).toBe(count)
    animation.destroy()
  })

  it('caps rendering at 60 Hz and resumes without creating duplicate loops', () => {
    const { animation, context } = setup()
    animation.tick(8)
    expect(context.drawImage).toHaveBeenCalledTimes(animation.amount)
    animation.tick(17)
    expect(context.drawImage).toHaveBeenCalledTimes(animation.amount * 2)
    animation.stop()
    expect(cancelAnimationFrame).toHaveBeenCalled()
    animation.play()
    const calls = vi.mocked(requestAnimationFrame).mock.calls.length
    animation.play()
    expect(requestAnimationFrame).toHaveBeenCalledTimes(calls)
    animation.destroy()
  })

  it('pauses in hidden tabs and cleans up listeners and pending resize on destroy', () => {
    vi.useFakeTimers()
    const { animation } = setup()
    const resize = vi.spyOn(animation, 'resize')
    vi.spyOn(document, 'hidden', 'get').mockReturnValue(true)
    document.dispatchEvent(new Event('visibilitychange'))
    expect(animation.frameId).toBeNull()
    vi.spyOn(document, 'hidden', 'get').mockReturnValue(false)
    document.dispatchEvent(new Event('visibilitychange'))
    expect(animation.frameId).not.toBeNull()
    window.dispatchEvent(new Event('resize'))
    animation.destroy()
    window.dispatchEvent(new Event('mousemove'))
    document.dispatchEvent(new Event('visibilitychange'))
    vi.runAllTimers()
    expect(resize).not.toHaveBeenCalled()
    expect(animation.mouse).toEqual({ x: 0, y: 0 })
    expect(animation.frameId).toBeNull()
  })

  it('resizes on narrow screens and coalesces resize events', () => {
    vi.useFakeTimers()
    const { animation } = setup()
    vi.stubGlobal('innerWidth', 375)
    vi.stubGlobal('innerHeight', 667)
    const resize = vi.spyOn(animation, 'resize')
    window.dispatchEvent(new Event('resize'))
    window.dispatchEvent(new Event('resize'))
    vi.advanceTimersByTime(100)
    expect(resize).toHaveBeenCalledTimes(1)
    expect(animation.canvas.width).toBe(375)
    expect(animation.canvas.height).toBe(667)
    animation.destroy()
  })
})
