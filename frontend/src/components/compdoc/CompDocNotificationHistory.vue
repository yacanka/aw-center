<script setup lang="ts">
import { formatTrackingTimestamp, type CompDocNotificationLog } from '@/services/compdocTracking'

defineProps<{ items: CompDocNotificationLog[] }>()
</script>

<template>
  <n-card title="Recent delivery activity" size="small">
    <n-empty v-if="!items.length" description="No notification attempts yet." />
    <div v-for="item in items" v-else :key="item.id" class="tracking-log">
      <n-flex justify="space-between">
        <n-text>{{ item.event_type.replaceAll('_', ' ') }}</n-text>
        <n-tag :type="item.status === 'sent' ? 'success' : 'error'" size="small">
          {{ item.status }}
        </n-tag>
      </n-flex>
      <n-text depth="3">
        {{ item.primary_recipient_count }} primary ·
        {{ item.escalation_recipient_count }} escalation · policy v{{ item.policy_version }} ·
        {{ formatTrackingTimestamp(item.created_at) }}
      </n-text>
    </div>
  </n-card>
</template>
