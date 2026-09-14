// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import ParticleAnimation from './particleTextAnimation.js'

function setup() {
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
  const animation = new ParticleAnimation(
    document.createElement('canvas'),
    ['#00000088'],
    'AW Center'
  )
  return { animation, context }
}

afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
  vi.useRealTimers()
})

describe('welcome particle animation', () => {
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

  it('preserves the original screen-aligned two-pixel sampling grid', () => {
    vi.stubGlobal('innerWidth', 1279)
    vi.stubGlobal('innerHeight', 719)
    const { animation, context } = setup()
    for (const particle of animation.particles) {
      expect(particle.dest.x % 2).toBe(0)
      expect(particle.dest.y % 2).toBe(0)
    }
    const first = animation.particles[0]
    expect(context.fillText).toHaveBeenCalledWith(
      'AW Center',
      window.innerWidth / 2 - first.dest.x,
      window.innerHeight / 2 - first.dest.y
    )
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
