<template>
  <n-space vertical justify="space-around">
    <n-space justify="space-around">
      <n-card v-if="props.compdoc.ubm_target_date"
        >UBM Target Date: {{ props.compdoc.ubm_target_date }}</n-card
      >
      <n-card v-if="props.compdoc.ubm_delivery_date"
        >UBM Delivery Date: {{ props.compdoc.ubm_delivery_date }}</n-card
      >
      <n-card v-if="props.compdoc.signature_panel"
        >Signature Panel: {{ props.compdoc.signature_panel }}</n-card
      >
      <n-card v-if="props.compdoc.responsible">Responsible: {{ props.compdoc.responsible }}</n-card>
      <n-card v-if="props.compdoc.moc">MoC: {{ props.compdoc.moc }}</n-card>
    </n-space>
    <n-card v-if="props.compdoc.notes">Notes: {{ props.compdoc.notes }}</n-card>
    <CompDocDccHistory
      v-if="props.compdoc.id"
      :project="project"
      :compdoc-id="props.compdoc.id"
      :allowed="canViewDccHistory"
    />
  </n-space>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import CompDocDccHistory from '@/components/compdoc/CompDocDccHistory.vue'
import type { ICompDoc } from '@/models/compdocs'
import { useUserStore } from '@/stores/user'

const props = defineProps<{ compdoc: ICompDoc }>()
const route = useRoute()
const userStore = useUserStore()
const project = computed(() => String(route.params.project || ''))
const canViewDccHistory = computed(() => userStore.hasEffectiveRole('dcc', 'view_jira_dcc'))
</script>
