<script setup lang="ts">
import { computed, ref, onMounted, onUnmounted } from 'vue'
import { useSessionStore } from '@/features/session/stores/session'
import { resolvePreferredTheme } from '@/app/services/theme'
import { useRouter } from 'vue-router'
import ParticleText from '@/shared/components/ParticleTextAnimator.vue'
const router = useRouter()

const particleText = ref<InstanceType<typeof ParticleText> | null>(null)
const session = useSessionStore()
const particleColors = computed(() => [
  resolvePreferredTheme(session.getPreferences) === 'dark' ? '#ffffff88' : '#00000088'
])
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
  <div class="welcome-background">
    <ParticleText ref="particleText" text="AW Center" :colors="particleColors" />
  </div>
</template>

<style scoped>
.welcome-background {
  position: relative;
  width: 100%;
  height: 100dvh;
  overflow: hidden;
}
</style>
