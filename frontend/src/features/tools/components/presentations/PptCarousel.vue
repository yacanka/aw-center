<script setup lang="ts">
import { ref, watch } from 'vue'
import { usePresentationController } from '@/features/tools/composables/presentationController'
import type { PresentationSlide } from '@/features/tools/models/presentation'
import { NCarousel, NButton, NUpload } from 'naive-ui'
import { Edit24Regular, Delete24Regular } from '@vicons/fluent'

const props = defineProps<{ presentationId: string; title: string }>()
const slides = ref<PresentationSlide[]>([])
const controller = usePresentationController()

async function load() {
  try {
    const data = await controller.loadPresentation(props.presentationId)
    slides.value = data.slides
  } catch {
    slides.value = []
  }
}

async function removeSlide(id: string) {
  try {
    await controller.deleteSlide(id)
    window.$message.success('Slide deleted')
    await load()
  } catch {
    // The domain store already presents the API error.
  }
}

async function updateSlide(id: string, file?: File | null) {
  if (!file) return
  const form = new FormData()
  form.append('image', file)
  try {
    await controller.updateSlide(id, form)
    window.$message.success('Slide updated')
    await load()
  } catch {
    // The domain store already presents the API error.
  }
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
        <div class="slide-content">
          <n-space justify="end" style="gap: 8px">
            <n-upload
              :default-upload="false"
              :on-change="(o) => updateSlide(s.id, o.file.file)"
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
          <img class="slide-image" :src="s.image_url" :alt="`${title} · slide ${s.index}`" />
        </div>
      </n-carousel-item>
    </n-carousel>
  </div>
</template>

<style scoped>
.slide-content {
  display: grid;
  gap: 8px;
  margin-inline: auto;
  max-width: 1200px;
  width: min(100%, 86%);
}

.slide-image {
  display: block;
  height: auto;
  max-height: 72dvh;
  max-width: 100%;
  object-fit: contain;
  width: 100%;
}

@media (max-width: 640px) {
  .slide-content {
    width: 100%;
  }
}
</style>
