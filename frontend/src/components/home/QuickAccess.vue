<template>
  <n-card title="Quick access" size="small" class="home-card">
    <template #header-extra>
      <n-text depth="3">Recent and available to you</n-text>
    </template>
    <n-empty v-if="!commands.length" description="No tools are available." />
    <n-grid v-else cols="1 s:2" responsive="screen" :x-gap="8" :y-gap="8">
      <n-grid-item v-for="command in commands" :key="command.path">
        <n-button block secondary class="quick-action" @click="openCommand(command)">
          <span>
            <strong>{{ command.label }}</strong>
            <small>{{ command.category || 'AW Center' }}</small>
          </span>
        </n-button>
      </n-grid-item>
    </n-grid>
  </n-card>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import {
  buildNavigationCommands,
  mergeRecentCommand,
  selectQuickAccessCommands,
  type CommandSource,
  type NavigationCommand
} from '@/services/commandSearch'
import { quickCommandStorageKey, readJson, writeJson } from '@/services/storage'

const props = defineProps<{ options: CommandSource[]; userId?: number }>()
const router = useRouter()
const storageKey = quickCommandStorageKey(props.userId)
const recentPaths = ref(readJson<string[]>(storageKey, []))
const commands = computed(() =>
  selectQuickAccessCommands(buildNavigationCommands(props.options), recentPaths.value)
)

function openCommand(command: NavigationCommand): void {
  recentPaths.value = mergeRecentCommand(recentPaths.value, command.path)
  writeJson(storageKey, recentPaths.value)
  void router.push(command.path)
}
</script>

<style scoped>
.home-card {
  height: 100%;
}

.quick-action {
  height: auto;
  justify-content: flex-start;
  padding: 10px 12px;
  text-align: left;
}

.quick-action span {
  display: grid;
  gap: 2px;
  width: 100%;
}

.quick-action small {
  opacity: 0.65;
}
</style>
