export default class ParticleAnimation {
  constructor(canvas, colors, text, heading) {
    this.canvas = canvas
    this.ctx = canvas.getContext('2d')
    this.colors = colors
    this.text = text
    this.heading = heading
    this.particles = []
    this.sprites = new Map()
    this.mouse = { x: 0, y: 0 }
    this.radius = 1
    this.playing = true
    this.frameId = null
    this.lastFrameTime = null
    this.resizeTimer = null
    this.tick = (time) => this.render(time)

    this.configureCanvas()

    this.mouseRadius = Math.min(this.ww / 10, 80)
    this.size = 3
    this.amount = 0

    this.initScene()
    this.addEventListeners()
    this.render()
  }

  configureCanvas() {
    const bounds = this.canvas.getBoundingClientRect()
    this.ww = Math.max(1, bounds.width)
    this.wh = Math.max(1, bounds.height)
    // Retain sharp edges on Retina screens without unbounded full-screen buffers.
    const pixelRatio = Math.min(window.devicePixelRatio || 1, 2)
    this.pixelRatio = pixelRatio
    this.canvas.width = Math.round(this.ww * pixelRatio)
    this.canvas.height = Math.round(this.wh * pixelRatio)
    this.ctx.setTransform(pixelRatio, 0, 0, pixelRatio, 0, 0)
  }

  initScene() {
    // Read pixels only from the text mask; keep the visible canvas GPU eligible.
    const mask = document.createElement('canvas')
    const ctx = mask.getContext('2d', { willReadFrequently: true })
    const style = getComputedStyle(this.heading)
    const fontSize = parseFloat(style.fontSize) || 60
    const fontFamily = style.fontFamily || 'sans-serif'
    const headingBounds = this.heading.getBoundingClientRect()
    const canvasBounds = this.canvas.getBoundingClientRect()
    const offsetX = Math.floor((headingBounds.left - canvasBounds.left) / this.size) * this.size
    const offsetY = Math.floor((headingBounds.top - canvasBounds.top) / this.size) * this.size
    mask.width = Math.max(1, Math.min(this.ww, Math.ceil(headingBounds.width + fontSize / 2)))
    mask.height = Math.max(1, Math.min(this.wh, Math.ceil(headingBounds.height + fontSize / 2)))
    ctx.font = `${style.fontWeight} ${fontSize}px ${fontFamily}`
    ctx.letterSpacing = style.letterSpacing
    ctx.textAlign = 'left'
    ctx.textBaseline = 'top'
    for (const line of this.heading.querySelectorAll('.particle-line')) {
      const bounds = line.getBoundingClientRect()
      ctx.fillText(
        line.textContent,
        bounds.left - canvasBounds.left - offsetX,
        bounds.top - canvasBounds.top - offsetY
      )
    }
    const data = ctx.getImageData(0, 0, mask.width, mask.height).data
    this.particles = []
    for (let x = 0; x < mask.width; x += this.size) {
      for (let y = 0; y < mask.height; y += this.size) {
        if (data[(x + y * mask.width) * 4 + 3] > 0) {
          this.particles.push(new Particle(x + offsetX, y + offsetY, this.colors))
        }
      }
    }

    this.amount = this.particles.length
    this.createSprites()
  }

  createSprites() {
    const radius = this.ww <= 500 ? 0.9 : 1
    this.spriteSize = Math.ceil(radius * 2 + 2)
    this.sprites.clear()
    for (const color of new Set(this.colors)) {
      const sprite = document.createElement('canvas')
      sprite.width = sprite.height = Math.ceil(this.spriteSize * this.pixelRatio)
      const ctx = sprite.getContext('2d')
      const scale = sprite.width / this.spriteSize
      ctx.setTransform(scale, 0, 0, scale, 0, 0)
      ctx.fillStyle = color
      ctx.beginPath()
      ctx.arc(this.spriteSize / 2, this.spriteSize / 2, radius, 0, Math.PI * 2)
      ctx.fill()
      this.sprites.set(color, sprite)
    }
  }

  addEventListeners() {
    this.listeners = {
      resize: () => {
        clearTimeout(this.resizeTimer)
        this.resizeTimer = setTimeout(() => this.resize(), 100)
      },
      mousemove: (event) => this.onMouseMove(event),
      touchmove: (event) => this.onTouchMove(event),
      click: () => this.onMouseClick(),
      touchend: () => this.onTouchEnd(),
      mouseleave: () => this.onTouchEnd()
    }
    this.listeners.scroll = this.listeners.resize
    for (const [name, listener] of Object.entries(this.listeners)) {
      window.addEventListener(name, listener, { passive: true })
    }
    this.resizeObserver = new ResizeObserver(this.listeners.resize)
    this.resizeObserver.observe(this.heading)
    this.onVisibilityChange = () => {
      this.cancelFrame()
      if (this.playing && !document.hidden) this.render()
    }
    document.addEventListener('visibilitychange', this.onVisibilityChange)
  }

  onMouseMove(e) {
    const bounds = this.canvas.getBoundingClientRect()
    this.mouse.x = e.clientX - bounds.left
    this.mouse.y = e.clientY - bounds.top
  }

  onTouchMove(e) {
    if (e.touches.length > 0) {
      this.onMouseMove(e.touches[0])
    }
  }

  onTouchEnd() {
    this.mouse.x = -100
    this.mouse.y = -100
  }

  onMouseClick() {
    this.radius = (this.radius + 1) % 3
  }

  resize() {
    this.configureCanvas()
    this.mouseRadius = Math.min(this.ww / 10, 80)
    this.initScene()
  }

  setColors(colors) {
    this.colors = colors
    this.createSprites()
    for (const particle of this.particles) {
      particle.color = colors[Math.floor(Math.random() * colors.length)]
    }
  }

  render(time = 0) {
    if (!this.playing || document.hidden) return
    this.frameId = requestAnimationFrame(this.tick)
    // Keep the original 60 Hz physics, without extra work on 120/144 Hz displays.
    const interval = 1000 / 60
    if (this.lastFrameTime !== null && time - this.lastFrameTime < interval - 0.5) return
    this.lastFrameTime =
      this.lastFrameTime === null
        ? time
        : this.lastFrameTime + Math.floor((time - this.lastFrameTime + 0.5) / interval) * interval
    this.ctx.clearRect(0, 0, this.ww, this.wh)
    // Composite each translucent particle separately, as in main. A shared path
    // loses the overlapping alpha that gives the text its soft, filled outline.
    const halfSize = this.spriteSize / 2
    for (const particle of this.particles) {
      particle.update(this.mouse, this.radius, this.mouseRadius)
      this.ctx.drawImage(
        this.sprites.get(particle.color),
        particle.x - halfSize,
        particle.y - halfSize,
        this.spriteSize,
        this.spriteSize
      )
    }
  }

  cancelFrame() {
    if (this.frameId !== null) cancelAnimationFrame(this.frameId)
    this.frameId = null
    this.lastFrameTime = null
  }

  stop() {
    this.playing = false
    this.cancelFrame()
  }

  play() {
    if (this.playing) return
    this.playing = true
    this.render()
  }

  destroy() {
    this.stop()
    this.resizeObserver.disconnect()
    clearTimeout(this.resizeTimer)
    for (const [name, listener] of Object.entries(this.listeners)) {
      window.removeEventListener(name, listener)
    }
    document.removeEventListener('visibilitychange', this.onVisibilityChange)
  }
}

class Particle {
  constructor(x, y, colors) {
    this.x = x
    this.y = y
    this.dest = { x, y }

    this.vx = 0
    this.vy = 0
    this.accX = 0
    this.accY = 0
    this.friction = Math.random() * 0.035 + 0.92
    this.color = colors[Math.floor(Math.random() * colors.length)]
  }

  update(mouse, radius, mouseRadius) {
    this.accX = (this.dest.x - this.x) / 300
    this.accY = (this.dest.y - this.y) / 300
    this.vx += this.accX
    this.vy += this.accY
    this.vx *= this.friction
    this.vy *= this.friction

    this.x += this.vx
    this.y += this.vy

    const dx = this.x - mouse.x
    const dy = this.y - mouse.y
    const interactionRadius = mouseRadius * radius

    if (dx * dx + dy * dy < interactionRadius * interactionRadius) {
      this.accX = (this.x - mouse.x) / 50
      this.accY = (this.y - mouse.y) / 50
      this.vx += this.accX
      this.vy += this.accY
    }
  }
}
