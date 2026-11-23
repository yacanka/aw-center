<script setup lang="ts">
import { Document24Regular } from '@vicons/fluent'
import gokbey from '../assets/aircraft/gokbey.webp'
import kaan from '../assets/aircraft/kaan.webp'
import hurkus from '../assets/aircraft/hurkus.webp'
import hurjet from '../assets/aircraft/hurjet.webp'
import stc1 from '../assets/aircraft/stc1.webp'
import stc2 from '../assets/aircraft/stc2.webp'
import ozgur from '../assets/aircraft/ozgur.webp'

defineProps<{ family: string }>()

const aircraft = new Map([
  ['gokbey', gokbey],
  ['kaan', kaan],
  ['hurkus', hurkus],
  ['hurjet', hurjet],
  ['stc1', stc1],
  ['stc2', stc2],
  ['ozgur', ozgur]
])
</script>

<template>
  <span class="artwork" aria-hidden="true">
    <img v-if="aircraft.has(family)" :src="aircraft.get(family)" alt="" decoding="async" />
    <n-icon v-else size="clamp(1.6rem, 5cqw, 3rem)"><Document24Regular /></n-icon>
  </span>
</template>

<style scoped>
.artwork {
  position: relative;
  isolation: isolate;
  display: grid;
  place-items: center;
  width: 100%;
  aspect-ratio: 1.62;
  color: var(--board-text);
}

.artwork::before {
  position: absolute;
  z-index: -1;
  inset: 0 13%;
  content: '';
  border: 2px solid var(--frame-border);
  border-radius: clamp(16px, 4cqw, 48px);
  background: var(--board-surface);
  box-shadow: 0 6px 16px var(--board-shadow);
}

.artwork img {
  width: 98%;
  height: 94%;
  min-width: 0;
  min-height: 0;
  object-fit: contain;
  filter: drop-shadow(0 5px 5px var(--board-shadow));
}
</style>
