<template>
  <n-collapse @item-header-click="emit('open', $event)">
    <n-collapse-item title="Legacy field history" name="history">
      <n-scrollbar style="max-width: 100%">
        <n-timeline horizontal>
          <n-timeline-item
            v-for="(item, index) in history"
            :key="index"
            :type="item.history_type === 'Created' ? 'success' : 'warning'"
            :title="item.history_user"
            :time="item.history_date"
          />
          <n-text v-if="!history?.length">No historical records.</n-text>
        </n-timeline>
      </n-scrollbar>
    </n-collapse-item>
  </n-collapse>
</template>

<script setup lang="ts">
import type { IHistory } from '@/features/compliance/models/compdocs'

defineProps<{ history?: IHistory[] | null }>()
const emit = defineEmits<{ open: [value: { expanded?: boolean }] }>()
</script>
