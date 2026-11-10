<script setup lang="ts">
import { ref, watch, onMounted, onUnmounted, nextTick } from 'vue'
import ParticleAnimation from '@/shared/utils/particleTextAnimation.js'

const props = defineProps<{ text: string; colors: string[] }>()
const heading = ref<HTMLElement | null>(null)
const canvas = ref<HTMLCanvasElement | null>(null)
const animated = ref(false)
let animation: ParticleAnimation | null = null
let motionPreference: MediaQueryList | null = null
let disposed = false

async function updateMotion() {
  animation?.destroy()
  animation = null
  animated.value = !motionPreference?.matches
  await nextTick()
  if (disposed || !animated.value || !canvas.value || !heading.value) return
  animation = new ParticleAnimation(canvas.value, props.colors, props.text, heading.value)
}

onMounted(() => {
  motionPreference = window.matchMedia('(prefers-reduced-motion: reduce)')
  motionPreference.addEventListener('change', updateMotion)
  void updateMotion()
})
watch(
  () => props.colors,
  (colors) => animation?.setColors(colors)
)
onUnmounted(() => {
  disposed = true
  motionPreference?.removeEventListener('change', updateMotion)
  animation?.destroy()
})
</script>

<template>
  <span ref="heading" class="particle-heading">
    <span class="accessible-text">{{ text }}</span>
    <span
      v-for="line in text.split(' ')"
      :key="line"
      class="particle-line"
      :class="{ 'particle-line--hidden': animated }"
      aria-hidden="true"
      >{{ line }}</span
    >
  </span>
  <Teleport to="body">
    <canvas v-if="animated" ref="canvas" class="particle-text-canvas" aria-hidden="true"></canvas>
  </Teleport>
</template>

<style scoped>
.particle-heading {
  display: block;
}
.particle-line {
  display: block;
  white-space: nowrap;
}
.particle-line--hidden {
  visibility: hidden;
}
.particle-text-canvas {
  position: fixed;
  inset: 0;
  z-index: 1;
  width: 100vw;
  height: 100dvh;
  pointer-events: none;
}
.accessible-text {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
}
</style>
