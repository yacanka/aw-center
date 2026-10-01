<script setup lang="ts">
import { ref, watch, onMounted, onUnmounted, nextTick } from 'vue'
import ParticleAnimation from '@/shared/utils/particleTextAnimation.js'

const props = defineProps<{ text: string; colors: string[] }>()
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
  if (disposed || !animated.value || !canvas.value) return
  animation = new ParticleAnimation(canvas.value, props.colors, props.text)
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
  <span class="particle-heading">
    <span :class="{ 'accessible-text': animated }">{{ text }}</span>
    <canvas v-if="animated" ref="canvas" aria-hidden="true"></canvas>
  </span>
</template>

<style scoped>
.particle-heading {
  position: relative;
  display: block;
  height: 1.3em;
}
canvas {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  font: inherit;
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
