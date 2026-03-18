<template>
  <div class="particle-background">
    <div v-for="(particle, index) in particles" :key="index" class="particle" :style="{
      top: '-5vh',
      left: `${particle.left}%`,
      width: `${particle.size}px`,
      height: `${particle.size}px`,
      boxShadow: `0 0 ${particle.blur}px ${theme == 'dark' ? '#ffffff' : '#000000'}, 0 0 ${particle.blur * 1.5}px ${theme == 'dark' ? '#ffffff' : '#000000'}`,
      animationDuration: `${particle.duration}s`,
      animationDelay: `${particle.delay}s`
    }"></div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useUserStore } from '@/stores/user'

const theme = useUserStore().getPreferences.theme

const particleCount = 50

const particles = ref([])

const random = (min, max) => Math.floor(Math.random() * (max - min) + min)

const createParticles = () => {
  const newParticles = []

  for (let i = 0; i < particleCount; i++) {
    newParticles.push({
      left: random(0, 100),
      size: random(2, 5),
      blur: random(6, 15),
      duration: random(50, 150),
      delay: random(0, 100)
    })
  }

  particles.value = newParticles
}

onMounted(() => {
  createParticles()
})
</script>

<style scoped>
.particle-background {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  pointer-events: none;
  overflow: hidden;
}

.particle {
  position: absolute;
  background: #606060;
  border-radius: 50%;
  opacity: 0.8;
  animation: rise linear infinite;
}

@keyframes rise {
  0% {
    transform: translateY(110vh) rotate(0deg);
    opacity: 0;
  }

  15% {
    opacity: 0.8;
  }

  90% {
    opacity: 0.8;
  }

  100% {
    transform: translateY(-20vh) rotate(360deg);
    opacity: 0;
  }
}

.content {
  color: white;
  font-size: 2.5rem;
  text-align: center;
  z-index: 10;
  text-shadow: 0 2px 10px rgba(0, 0, 0, 0.5);
}
</style>