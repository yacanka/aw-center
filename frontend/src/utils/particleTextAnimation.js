export default class ParticleAnimation {
  constructor(canvas, colors, text) {
    this.canvas = canvas;
    this.ctx = canvas.getContext('2d', { willReadFrequently: true });
    this.colors = colors;
    this.text = text;
    this.particles = [];
    this.mouse = { x: 0, y: 0 };
    this.radius = 1;
    this.playing = true;

    this.ww = this.canvas.width = window.innerWidth;
    this.wh = this.canvas.height = window.innerHeight;

    this.mouseRadius = Math.min(this.ww / 10, 80);
    this.size = 2;
    this.amount = 0;

    this.initScene();
    this.addEventListeners();
    this.render();
  }

  initScene() {
    this.ctx.clearRect(0, 0, this.ww, this.wh);
    this.ctx.font = '900 ' + Math.max(this.wh / 8, 60) + 'px Quicksand';
    this.ctx.textAlign = 'center';
    this.ctx.textBaseline = 'middle';
    this.ctx.fillStyle = '#fff';
    this.ctx.fillText(this.text, this.ww / 2, this.wh / 2);

    const imageData = this.ctx.getImageData(0, 0, this.ww, this.wh);
    const data = imageData.data;

    this.particles = [];
    const step = this.size;

    for (let i = 0; i < this.ww; i += step) {
      for (let j = 0; j < this.wh; j += step) {
        const idx = (i + j * this.ww) * 4;
        if (data[idx + 3] > 0) { // Alpha > 0
          this.particles.push(new Particle(i, j, this.colors, this.ww, this.wh));
        }
      }
    }

    this.amount = this.particles.length;
  }

  addEventListeners() {
    window.addEventListener('resize', () => this.resize());
    window.addEventListener('mousemove', (e) => this.onMouseMove(e));
    window.addEventListener('touchmove', (e) => this.onTouchMove(e));
    window.addEventListener('click', () => this.onMouseClick());
    window.addEventListener('touchend', () => this.onTouchEnd());
  }

  onMouseMove(e) {
    this.mouse.x = e.clientX;
    this.mouse.y = e.clientY;
  }

  onTouchMove(e) {
    if (e.touches.length > 0) {
      this.mouse.x = e.touches[0].clientX;
      this.mouse.y = e.touches[0].clientY;
    }
  }

  onTouchEnd() {
    this.mouse.x = -100;
    this.mouse.y = -100;
  }

  onMouseClick() {
    this.radius = (this.radius + 1) % 3;
  }

  resize() {
    if (window.innerWidth > 500) {
      this.ww = this.canvas.width = window.innerWidth;
      this.wh = this.canvas.height = window.innerHeight;
      this.mouseRadius = Math.min(this.ww / 10, 80);
      this.initScene();
    }
  }

  render() {
    requestAnimationFrame(() => {
      if (this.playing) this.render();
    });

    this.ctx.clearRect(0, 0, this.ww, this.wh);

    for (let i = 0; i < this.amount; i++) {
      this.particles[i].render(this.ctx, this.mouse, this.radius, this.mouseRadius);
    }
  }

  stop() {
    this.playing = false;
  }

  play() {
    this.playing = true;
  }
}

class Particle {
  constructor(x, y, colors, ww, wh) {
    this.x = ww / 2;
    this.y = wh / 2;
    this.r = ww <= 500 ? 1.2 : 2;
    this.dest = { x, y };

    const speed = Math.min(ww / 84, 20);
    this.vx = (Math.random() - 0.5) * speed;
    this.vy = (Math.random() - 0.5) * speed;
    this.accX = 0;
    this.accY = 0;
    this.friction = Math.random() * 0.035 + 0.92;
    this.color = colors[Math.floor(Math.random() * colors.length)];
  }

  render(ctx, mouse, radius, mouseRadius) {
    this.accX = (this.dest.x - this.x) / 300;
    this.accY = (this.dest.y - this.y) / 300;
    this.vx += this.accX;
    this.vy += this.accY;
    this.vx *= this.friction;
    this.vy *= this.friction;

    this.x += this.vx;
    this.y += this.vy;

    const dx = this.x - mouse.x;
    const dy = this.y - mouse.y;
    const distance = Math.hypot(dx, dy);

    if (distance < mouseRadius * radius) {
      this.accX = (this.x - mouse.x) / 50;
      this.accY = (this.y - mouse.y) / 50;
      this.vx += this.accX;
      this.vy += this.accY;
    }

    ctx.fillStyle = this.color;
    ctx.beginPath();
    ctx.arc(this.x, this.y, this.r, 0, Math.PI * 2, false);
    ctx.fill();
  }
}