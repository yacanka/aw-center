<script setup lang="ts">
import { computed, useId } from 'vue'
import { Document24Regular } from '@vicons/fluent'
import board from '../assets/project-board.webp'

const props = defineProps<{ family: string }>()
const clipId = useId()
// Coordinates in the supplied board preserve the original aircraft extending past each frame.
const frames: Record<string, { x: number; y: number; outline: string }> = {
  gokbey: {
    x: 175,
    y: 253,
    outline:
      '161,250 331,273 396,276 427,291 373,298 464,341 483,363 489,389 462,409 451,398 206,422 175,420 174,402 207,399 276,320'
  },
  kaan: { x: 646, y: 249, outline: '897,357 944,354 1020,374 1019,380 926,380 880,389' },
  hurkus: {
    x: 1138,
    y: 244,
    outline:
      '1375,334 1457,273 1451,256 1466,254 1485,274 1468,278 1429,333 1462,340 1477,350 1471,364 1431,378 1394,383'
  },
  hurjet: { x: 176, y: 590, outline: '432,682 531,676 471,698 428,711' },
  stc1: {
    x: 648,
    y: 585,
    outline: '918,688 959,665 988,660 963,683 1013,708 995,712 953,701 938,728 915,730'
  },
  stc2: {
    x: 1139,
    y: 581,
    outline: '1411,663 1448,656 1481,660 1511,674 1505,686 1475,698 1413,719'
  }
}
const frame = computed(() => frames[props.family])
</script>

<template>
  <svg
    v-if="frame"
    :viewBox="`${frame.x - 44} ${frame.y - 10} 422 266`"
    aria-hidden="true"
    focusable="false"
  >
    <defs>
      <clipPath :id="clipId">
        <rect :x="frame.x" :y="frame.y" width="296" height="252" rx="60" />
        <polygon :points="frame.outline" />
      </clipPath>
    </defs>
    <image :href="board" width="1536" height="957" :clip-path="`url(#${clipId})`" />
  </svg>
  <span v-else class="family-mark" aria-hidden="true"
    ><n-icon size="44"><Document24Regular /></n-icon
  ></span>
</template>
