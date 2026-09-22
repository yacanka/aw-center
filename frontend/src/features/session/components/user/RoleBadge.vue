<script setup lang="ts">
import { computed, ref } from 'vue'
import { NTooltip } from 'naive-ui'
import type { IGroup } from '@/features/session/models/auth'
import { roleDescription, isCriticalRole } from '@/features/session/services/userAccess'
const props = defineProps<{
  group?: IGroup
  name?: string
  description?: string
  critical?: boolean
}>()
const opened = ref(false)
const label = computed(() => props.name || props.group?.name || 'Role')
const explanation = computed(() => props.description || roleDescription(props.group || {}))
</script>
<template>
  <n-tooltip :show="opened" style="max-width: 300px">
    <template #trigger
      ><button
        type="button"
        class="role-badge"
        :class="{ critical: critical || (group && isCriticalRole(group)) }"
        :aria-label="`${label}: ${explanation}`"
        @mouseenter="opened = true"
        @mouseleave="opened = false"
        @focus="opened = true"
        @blur="opened = false"
        @click.stop="opened = !opened"
        @keydown.esc="opened = false"
      >
        {{ label }}
      </button></template
    >
    {{ explanation }}
  </n-tooltip>
</template>
<style scoped>
.role-badge {
  font: inherit;
  font-size: 12px;
  line-height: 1.4;
  border: 1px solid #dfe2e8;
  background: #f7f7f8;
  color: #454b58;
  padding: 4px 8px;
  border-radius: 4px;
  cursor: help;
  text-align: left;
  overflow-wrap: anywhere;
  max-width: 100%;
}
.critical {
  color: #002fa7;
  border-color: #c7d4ef;
  background: #f0f4ff;
}
.role-badge:focus-visible {
  outline: 2px solid #002fa7;
  outline-offset: 2px;
}
</style>
