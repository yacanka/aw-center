<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue';
import ParticleAnimation from "@/utils/particleTextAnimation.js";

const props = defineProps<{
    text: string,
    colors: string[]
}>()

const canvas = ref<HTMLCanvasElement | null>(null);

let obj: ParticleAnimation | null = null
onMounted(() => {
    if (canvas.value && obj == null) {
        obj = new ParticleAnimation(canvas.value, props.colors, props.text);
    }
});

onUnmounted(() => {
    if (obj) {
        obj = null
    }
})

function stopAnimation() {
    obj?.stop()
}

function playAnimation() {
    obj?.play()
}

defineExpose({ playAnimation, stopAnimation })
</script>

<template>
    <canvas id="particles-text-canvas" ref="canvas"></canvas>
</template>

<style>
#particles-text-canvas {
    position: absolute;
    overflow: hidden;
    width: 100%;
    height: 100%;
    will-change: transform;
}
</style>
