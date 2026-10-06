<script setup lang="ts">
import { computed, ref } from 'vue'
import { NIcon, type DropdownOption } from 'naive-ui'
import { MoreHorizontal20Regular } from '@vicons/fluent'
import type { IDcc } from '../models/dcc'
const props = defineProps<{ record: IDcc; canEdit: boolean; busy: boolean }>()
const emit = defineEmits<{ details: []; reminder: []; check: []; edit: []; remove: [] }>()
const menuOpen = ref(false)
function nodeProps(option: DropdownOption) {
  return { role: 'menuitem', 'aria-disabled': Boolean(option.disabled) }
}
const options = computed(() => [
  { label: 'Check status', key: 'check', disabled: props.busy },
  { label: 'Edit', key: 'edit', disabled: !props.canEdit },
  { type: 'divider', key: 'divider' },
  { label: 'Remove', key: 'remove', disabled: !props.canEdit }
])
function select(key: string): void {
  if (key === 'check') emit('check')
  if (key === 'edit') emit('edit')
  if (key === 'remove') emit('remove')
}
</script>
<template>
  <div class="record-actions">
    <n-button secondary type="primary" @click="emit('details')">Details</n-button>
    <n-button
      :disabled="!record.active || !canEdit"
      aria-label="Send reminder"
      @click="emit('reminder')"
      >Remind</n-button
    >
    <n-dropdown
      v-model:show="menuOpen"
      trigger="click"
      :options="options"
      :node-props="nodeProps"
      :menu-props="() => ({ role: 'menu', 'aria-label': `Actions for ${record.issue}` })"
      @select="select"
    >
      <n-button
        :aria-label="`More actions for ${record.issue}`"
        aria-haspopup="menu"
        :aria-expanded="menuOpen"
        class="more-actions"
      >
        <template #icon
          ><n-icon :component="MoreHorizontal20Regular" aria-hidden="true"
        /></template>
      </n-button>
    </n-dropdown>
  </div>
</template>
<style scoped>
.record-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}
.record-actions :deep(.n-button) {
  min-height: 44px;
}
.more-actions {
  min-width: 44px;
}
</style>
