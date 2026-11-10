<script setup lang="ts">
import { ref } from 'vue'
import { NTooltip, NIcon } from 'naive-ui'
import { QuestionCircle20Regular } from '@vicons/fluent'
import type { IPermission } from '@/features/session/models/auth'
import { permissionDescription, permissionKey } from '@/features/session/services/userAccess'

defineProps<{ permission: IPermission }>()
const focused = ref(false)
</script>

<template>
  <span class="permission-label">
    <span>{{ permission.name || permission.codename }}</span>
    <n-tooltip :show="focused || undefined" trigger="hover" style="max-width: 340px">
      <template #trigger>
        <button
          type="button"
          class="permission-help"
          :aria-label="`About ${permission.name || permission.codename}`"
          @focus="focused = true"
          @blur="focused = false"
          @keydown.esc="focused = false"
          @click.stop="focused = !focused"
        >
          <n-icon :component="QuestionCircle20Regular" :size="16" />
        </button>
      </template>
      {{ permissionDescription(permission) }}
      <br />{{ permissionKey(permission) }}
    </n-tooltip>
  </span>
</template>

<style scoped>
.permission-label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.permission-help {
  display: inline-flex;
  color: inherit;
  background: none;
  border: 0;
  padding: 2px;
  cursor: help;
}
.permission-help:focus-visible {
  outline: 2px solid currentColor;
  outline-offset: 2px;
}
</style>
