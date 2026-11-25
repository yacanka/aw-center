<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useThemeVars } from 'naive-ui'
import { useProjectCatalogStore } from '@/features/projects/stores/projectCatalog'
import { certificationCards } from '../models/certificationProjects'
import CertificationArtwork from '../components/CertificationArtwork.vue'
import DashboardExecutableDownload from '../components/DashboardExecutableDownload.vue'

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
      <n-button
        v-for="card in cards"
        :key="card.key"
        class="project-card"
        text
        block
        :aria-haspopup="card.members.length > 1 ? 'dialog' : undefined"
        @click="choose(card)"
      >
        <CertificationArtwork :family="card.key" />
        <span class="project-label">{{ card.label }}</span>
      </n-button>
    </div>
  </section>
  <n-flex v-if="cards.length" class="tools" align="center">
    <DashboardExecutableDownload :project="cards[0].members[0].slug" />
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
  padding: clamp(12px, 3.5vw, 48px);
  border-radius: v-bind('theme.borderRadius');
  container-type: inline-size;
  --board-surface: color-mix(
    in srgb,
    light-dark(v-bind('theme.invertedColor'), v-bind('theme.cardColor')) 85%,
    v-bind('theme.infoColor')
  );
  --board-text: light-dark(v-bind('theme.baseColor'), v-bind('theme.textColorBase'));
  --board-shadow: color-mix(in srgb, var(--board-surface) 50%, transparent);
  --frame-border: color-mix(in srgb, var(--board-text) 76%, var(--board-surface));
  background:
    linear-gradient(180deg, var(--board-shadow), var(--board-surface)),
    center top / cover url('../assets/mountain-sky.webp') var(--board-surface);
}
h1,
.project-label {
  color: var(--board-text);
  background: var(--board-surface);
}
h1 {
  margin: 0 0 clamp(18px, 3.3cqw, 46px);
  padding: 0.55em 0.7em;
  border: 2px solid currentColor;
  border-radius: 0.5em;
  text-align: center;
  text-transform: uppercase;
  font-size: clamp(1.25rem, 3.5cqw, 2.75rem);
  line-height: 1.15;
}
.project-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: clamp(14px, 2.7cqw, 36px);
}
.project-card {
  align-self: start;
  border-radius: 12px;
  white-space: normal;
}
.project-card :deep(.n-button__content) {
  flex-direction: column;
  width: 100%;
  gap: clamp(6px, 1.2cqw, 12px);
}
.project-card:focus-visible {
  outline: 3px solid var(--board-text);
  outline-offset: 2px;
  box-shadow: 0 0 0 2px var(--board-surface);
}
.project-label {
  max-width: 100%;
  padding: 0.28em 0.65em;
  border-radius: 0.3em;
  font-size: clamp(0.875rem, 1.65cqw, 1.375rem);
  font-weight: 700;
  line-height: 1.2;
  overflow-wrap: anywhere;
}
.project-card:is(:hover, :focus-visible) {
  --frame-border: var(--board-text);
}
.project-card:is(:hover, :focus-visible) .project-label {
  text-decoration: underline;
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
