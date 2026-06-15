<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import ParticleText from '@/components/ParticleTextAnimator.vue'
import { isAuthenticated } from '@/stores/user'

const welcomeSeenStorageKey = 'aw-center:welcome-seen'
const welcomeDurationMilliseconds = 8000

const router = useRouter()
const particleText = ref<InstanceType<typeof ParticleText> | null>(null)
const shouldShowWelcome = ref(localStorage.getItem(welcomeSeenStorageKey) !== 'true')
let welcomeTimer: number | undefined

function resolveNextRouteName() {
  return isAuthenticated() ? 'home' : 'login'
}

function redirectAfterWelcome() {
  localStorage.setItem(welcomeSeenStorageKey, 'true')
  particleText.value?.stopAnimation()
  router.replace({ name: resolveNextRouteName() })
}

onMounted(() => {
  if (!shouldShowWelcome.value) {
    router.replace({ name: resolveNextRouteName() })
    return
  }

  welcomeTimer = window.setTimeout(redirectAfterWelcome, welcomeDurationMilliseconds)
})

onBeforeUnmount(() => {
  if (welcomeTimer) window.clearTimeout(welcomeTimer)
})
</script>

<template>
  <div v-if="shouldShowWelcome" class="welcome-screen">
    <video loop muted autoplay playsinline preload="metadata" poster="/welcome-poster.svg" class="background-video">
      <source src="/world.mp4" type="video/mp4" />
    </video>
    <ParticleText ref="particleText" text="AW Center" :colors="['#ffffff88']" class="particle-text" />
  </div>
</template>

<style scoped>
.welcome-screen {
  position: relative;
  width: 100%;
  height: 100vh;
  overflow: hidden;
  background:
    radial-gradient(circle at 28% 18%, rgb(94 231 255 / 55%), transparent 48%),
    radial-gradient(circle at 78% 82%, rgb(141 92 255 / 45%), transparent 55%),
    linear-gradient(135deg, #07111f 0%, #10264f 55%, #030712 100%);
}

.background-video,
.particle-text {
  position: absolute;
  top: 50%;
  left: 50%;
  width: 100%;
  height: 100%;
  transform: translate(-50%, -50%);
  pointer-events: none;
}

.background-video {
  object-fit: cover;
}
</style>
