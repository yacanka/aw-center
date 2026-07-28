<script setup lang="ts">
import { ref, watch } from 'vue'
import { usePptxStore } from '@/stores/presentations'
import type { PresentationSlide } from '@/models/presentation'
import { NCarousel, NButton, NUpload } from 'naive-ui'
import { Edit24Regular, Delete24Regular } from '@vicons/fluent'

const props = defineProps<{ presentationId: number; title: string }>()
const slides = ref<PresentationSlide[]>([])
const store = usePptxStore()

async function load() {
  const data = await store.loadSlide(props.presentationId)
  slides.value = data.slides
}

async function removeSlide(id: number) {
  await store.deleteSlide(id)
  window.$message.success('Slide deleted')
  load()
}

async function updateSlide(id: number, file: File) {
  const form = new FormData()
  form.append('image', file)
  await store.updateSlide(id, form)
  window.$message.success('Slide updated')
  load()
}

watch(() => props.presentationId, load, { immediate: true })
</script>

<template>
  <div>
    <n-flex justify="center">
      <h2>{{ title }}</h2>
    </n-flex>

    <n-carousel autoplay draggable keyboard>
      <n-carousel-item v-for="s in slides" :key="s.id">
        <n-space vertical align="center" item-style="width: 80.75%" style="gap: 4px">
          <n-space justify="end" style="gap: 8px">
            <n-upload
              :default-upload="false"
              :on-change="(o) => updateSlide(s.id, o.file!.file as File)"
              style="display: flex"
            >
              <n-button ghost size="tiny" type="warning" style="margin: 0px">
                <template #icon>
                  <Edit24Regular style="margin: 0px" />
                </template>
              </n-button>
            </n-upload>
            <n-button ghost size="tiny" type="error" @click="removeSlide(s.id)">
              <template #icon>
                <Delete24Regular />
              </template>
            </n-button>
          </n-space>
          <img :src="s.image" />
        </n-space>
      </n-carousel-item>
    </n-carousel>
  </div>
</template>
