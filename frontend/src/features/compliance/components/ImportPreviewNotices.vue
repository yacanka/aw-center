<script setup lang="ts">
import { NAlert, NCollapse, NCollapseItem } from 'naive-ui'
import type { ImportPreview } from '../api/compdocImports'

defineProps<{ preview: ImportPreview }>()
</script>

<template>
  <n-collapse class="import-notices">
    <n-collapse-item
      v-if="preview.unmapped_columns?.length"
      name="unmapped"
      title="There are unmapped columns"
    >
      <n-alert type="warning" :bordered="false">
        <ul>
          <li v-for="column in preview.unmapped_columns" :key="column">{{ column }}</li>
        </ul>
      </n-alert>
    </n-collapse-item>
    <n-collapse-item
      v-if="preview.status_changes?.length"
      name="statuses"
      title="New project statuses"
    >
      <n-alert type="info" :bordered="false">
        <ul>
          <li v-for="status in preview.status_changes" :key="status.value">{{ status.label }}</li>
        </ul>
      </n-alert>
    </n-collapse-item>
    <n-collapse-item
      v-if="preview.panel_changes?.length"
      name="panels"
      title="Project panel changes"
    >
      <n-alert type="info" :bordered="false">
        These changes also apply to other documents using the same ATA chapter.
        <ul>
          <li v-for="change in preview.panel_changes" :key="change.ata">
            {{ change.action === 'create' ? 'Create' : 'Update' }} {{ change.ata }}:
            {{ change.old_name ? `${change.old_name} → ` : '' }}{{ change.new_name }}
          </li>
        </ul>
      </n-alert>
    </n-collapse-item>
  </n-collapse>
</template>

<style scoped>
.import-notices {
  margin: 12px 0;
}
ul {
  margin: 0;
  padding-left: 20px;
  overflow-wrap: anywhere;
}
</style>
