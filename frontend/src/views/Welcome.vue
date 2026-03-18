<script setup lang="ts">
import { h, ref, onMounted, DefineProps } from 'vue'
import { NButton, NDataTable, NSpace, NTag, NUpload } from 'naive-ui'
import { Settings16Regular, Door16Regular } from '@vicons/fluent';
import { useRouter } from 'vue-router'
import ParticleText from '@/components/ParticleTextAnimator.vue'
const router = useRouter()

const showNotification = ref(true)


const notificationValue = ref(1)
const username = ref(null)
const particleText = ref<InstanceType<typeof ParticleText> | null>(null)
const videoRef = ref(null)

onMounted(async () => {
    setTimeout(() => {
        if (particleText.value) {
            particleText.value.stopAnimation()
        }
        router.push({ name: "login" })
    }, 8000)
})
</script>

<template>
    <div class="bg-wrap">
        <video ref="videoRef" src="/world.mp4" loop muted autoplay playsinline preload="auto" class="bg-video" />
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