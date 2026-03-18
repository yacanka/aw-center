<script setup lang="ts">
import { ref } from 'vue'
import PptUploader from '@/components/pptxgallery/PptUploader.vue'
import PptList from '@/components/pptxgallery/PptList.vue'
import PptCarousel from '@/components/pptxgallery/PptCarousel.vue'

const selectedId = ref<number|null>(null)
const selectedTitle = ref<string>('')

function onSelect(p:{id:number,title:string}){
  selectedId.value = p.id
  selectedTitle.value = p.title
}
</script>

<template>
  <n-space vertical>
    <h1>PowerPoint Gallery</h1>
    <PptUploader @uploaded="onSelect" />
    <PptList @select="onSelect" />
    <PptCarousel v-if="selectedId" :presentation-id="selectedId" :title="selectedTitle" />
  </n-space>
</template>