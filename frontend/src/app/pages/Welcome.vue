<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import ParticleText from '@/shared/components/ParticleTextAnimator.vue'
const router = useRouter()

const particleText = ref<InstanceType<typeof ParticleText> | null>(null)
const welcomeVideoUrl = `${import.meta.env.BASE_URL}world.mp4`
let redirectTimer: ReturnType<typeof setTimeout> | null = null

onMounted(() => {
  redirectTimer = setTimeout(() => {
    if (particleText.value) {
      particleText.value.stopAnimation()
    }
    router.push({ name: 'login' })
  }, 8000)
})

onUnmounted(() => {
  if (redirectTimer) clearTimeout(redirectTimer)
})
</script>

<template>
  <div class="bg-wrap">
    <video
      ref="videoRef"
      :src="welcomeVideoUrl"
      loop
      muted
      autoplay
      playsinline
      preload="metadata"
      class="bg-video"
    />
  </div>
  <ParticleText ref="particleText" text="AW Center" :colors="['#ffffff88']" class="bg-video" />
</template>

<style>
.bg-wrap {
  position: relative;
  width: 100%;
  height: 100vh;
  overflow: hidden;
}

.bg-video {
  position: absolute;
  top: 50%;
  left: 50%;
  width: 100%;
  height: 100%;
  transform: translate(-50%, -50%);
  object-fit: cover;
  pointer-events: none;
}
</style>
