<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useThemeVars } from 'naive-ui'
import { useProjectCatalogStore } from '@/features/projects/stores/projectCatalog'
import { certificationCards } from '../models/certificationProjects'
import CertificationArtwork from '../components/CertificationArtwork.vue'

const catalog = useProjectCatalogStore()
const router = useRouter()
const theme = useThemeVars()
const cards = computed(() => certificationCards(catalog.complianceProjects))
const openFamily = ref('')
const selected = computed(() => cards.value.find((card) => card.key === openFamily.value))
function choose(card: (typeof cards.value)[number]) {
  if (card.members.length === 1) {
    void router.push({ name: 'certificationProject', params: { project: card.members[0].slug } })
  } else openFamily.value = card.key
}
function load() {
  void catalog.load().catch(() => undefined) // The store renders the failure on this page.
}
load()
</script>

<template>
  <section class="certification">
    <h1>Certification Dashboard</h1>
    <n-spin v-if="catalog.status === 'loading'" />
    <n-alert v-else-if="catalog.error" type="error">
      {{ catalog.error }} <n-button @click="load">Tekrar dene</n-button>
    </n-alert>
    <n-empty
      v-else-if="!cards.length"
      class="empty"
      description="Erişebileceğiniz proje bulunmuyor."
    />
    <div v-else class="project-grid">
      <button
        v-for="card in cards"
        :key="card.key"
        class="project-card"
        type="button"
        :aria-haspopup="card.members.length > 1 ? 'dialog' : undefined"
        @click="choose(card)"
      >
        <CertificationArtwork :family="card.key" />
        <span class="project-label">{{ card.label }}</span>
      </button>
    </div>
  </section>
  <n-flex v-if="cards.length" class="tools">
    <router-link :to="{ name: 'docAnalyzer' }">Doc Analyzer</router-link>
    <router-link :to="{ name: 'coverpagecreator' }">Cover Page Creator</router-link>
  </n-flex>
  <n-modal
    :show="!!selected"
    preset="card"
    :title="selected?.label"
    class="project-picker"
    @update:show="
      (show: boolean) => {
        if (!show) openFamily = ''
      }
    "
  >
    <n-flex vertical>
      <router-link
        v-for="item in selected?.members"
        :key="item.slug"
        custom
        :to="{ name: 'certificationProject', params: { project: item.slug } }"
        v-slot="{ href, navigate }"
      >
        <n-button tag="a" :href="href" @click="navigate">{{ item.name }}</n-button>
      </router-link>
    </n-flex>
  </n-modal>
</template>

<style scoped>
.certification {
  padding: clamp(12px, 2.5vw, 40px);
  border-radius: v-bind('theme.borderRadius');
  background: center top / cover url('../assets/mountain-sky.webp');
  container-type: inline-size;
  --board-surface: v-bind('theme.invertedColor');
  --board-text: color-mix(in srgb, white 96%, v-bind('theme.infoColor'));
}
h1,
.project-label,
.family-mark {
  color: var(--board-text);
  background: var(--board-surface);
}
h1 {
  margin: 0 0 clamp(18px, 3vw, 46px);
  padding: 0.45em 0.6em;
  border: 2px solid currentColor;
  border-radius: 0.5em;
  text-align: center;
  text-transform: uppercase;
  font-size: clamp(1.4rem, 4vw, 3rem);
  line-height: 1.15;
}
.project-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: clamp(14px, 2.3vw, 34px);
}
.project-card {
  display: grid;
  justify-items: center;
  align-content: start;
  gap: 6px;
  padding: 4px;
  min-width: 0;
  background: transparent;
  border: 0;
  cursor: pointer;
  font: inherit;
}
.project-card:focus-visible {
  outline: 3px solid var(--board-text);
  box-shadow: 0 0 0 5px var(--board-surface);
  border-radius: 12px;
}
.project-card svg {
  display: block;
  width: 100%;
}
.project-label {
  padding: 0.1em 0.6em;
  border-radius: 0.3em;
  font-size: clamp(1rem, 2vw, 1.5rem);
  font-weight: 750;
}
.project-card:hover .project-label {
  text-decoration: underline;
}
.family-mark {
  width: 70%;
  aspect-ratio: 296/252;
  margin-block: 2%;
  border: 2px solid var(--board-text);
  border-radius: 20%;
  display: grid;
  place-items: center;
}
.empty {
  background: v-bind('theme.cardColor');
  padding: 24px;
}
.tools {
  margin-block: 16px;
}
:global(.project-picker) {
  width: min(26rem, calc(100vw - 32px));
}
@container (max-width: 650px) {
  .project-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
@container (max-width: 270px) {
  .project-grid {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
