<template>
  <n-button class="command-trigger" secondary type="primary" @click="openPalette">
    Quick command <n-tag size="small">{{ shortcutLabel }}</n-tag>
  </n-button>
  <n-modal v-model:show="visible" preset="card" title="Quick command" class="command-modal">
    <n-input
      ref="inputReference"
      v-model:value="query"
      clearable
      autofocus
      aria-label="Search application commands"
      placeholder="Search a tool, process, or integration…"
      @keydown="handleSearchKeydown"
    />
    <div v-if="matches.length" class="command-results" role="listbox">
      <button
        v-for="(command, index) in matches"
        :key="command.path"
        type="button"
        class="command-row"
        :class="{ active: index === activeIndex }"
        :aria-selected="index === activeIndex"
        @mouseenter="activeIndex = index"
        @click="executeCommand(command)"
      >
        <span class="command-copy">
          <strong>{{ command.label }}</strong>
          <small>{{ command.category || 'AW Center' }}</small>
        </span>
        <n-tag size="small" :bordered="false">{{ command.path }}</n-tag>
      </button>
    </div>
    <n-empty v-else description="No matching command found." class="command-empty" />
    <template #footer>
      <n-text depth="3">↑↓ select · Enter open · Esc close · recent commands appear first</n-text>
    </template>
  </n-modal>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import type { InputInst } from 'naive-ui'
import { useRoute, useRouter } from 'vue-router'
import { quickCommandStorageKey, readJson, writeJson } from '@/services/storage'
import { useUserStore } from '@/stores/user'
import {
  buildNavigationCommands,
  mergeRecentCommand,
  prioritizeRecentCommands,
  searchNavigationCommands,
  type CommandSource,
  type NavigationCommand
} from '@/services/commandSearch'

const props = defineProps<{ options: CommandSource[] }>()
const router = useRouter()
const route = useRoute()
const userStore = useUserStore()
const visible = ref(false)
const query = ref('')
const activeIndex = ref(0)
const inputReference = ref<InputInst | null>(null)
const recentStorageKey = quickCommandStorageKey(userStore.getUser.id)
const recentPaths = ref(readJson<string[]>(recentStorageKey, []))
const shortcutLabel = /Mac|iPhone|iPad/.test(navigator.platform) ? '⌘ K' : 'Ctrl K'

const commands = computed(() => buildNavigationCommands(props.options))
const orderedCommands = computed(() => prioritizeRecentCommands(commands.value, recentPaths.value))
const matches = computed(() => searchNavigationCommands(orderedCommands.value, query.value))

watch(query, () => (activeIndex.value = 0))
watch(visible, (isVisible) => isVisible && void focusSearch())
watch(() => route.path, rememberVisitedCommand, { immediate: true })

onMounted(() => window.addEventListener('keydown', handleGlobalShortcut))
onBeforeUnmount(() => window.removeEventListener('keydown', handleGlobalShortcut))

function openPalette(): void {
  query.value = ''
  activeIndex.value = 0
  visible.value = true
}

async function focusSearch(): Promise<void> {
  await nextTick()
  inputReference.value?.focus()
}

function handleGlobalShortcut(event: KeyboardEvent): void {
  if (!(event.metaKey || event.ctrlKey) || event.key.toLowerCase() !== 'k') return
  event.preventDefault()
  visible.value ? (visible.value = false) : openPalette()
}

function handleSearchKeydown(event: KeyboardEvent): void {
  const actions: Record<string, () => void> = {
    ArrowDown: () => moveSelection(1),
    ArrowUp: () => moveSelection(-1),
    Enter: executeSelected
  }
  const action = actions[event.key]
  if (!action) return
  event.preventDefault()
  action()
}

function moveSelection(step: number): void {
  if (!matches.value.length) return
  const length = matches.value.length
  activeIndex.value = (activeIndex.value + step + length) % length
}

function executeSelected(): void {
  const command = matches.value[activeIndex.value]
  if (command) executeCommand(command)
}

function executeCommand(command: NavigationCommand): void {
  recentPaths.value = mergeRecentCommand(recentPaths.value, command.path)
  writeJson(recentStorageKey, recentPaths.value)
  visible.value = false
  void router.push(command.path)
}

function rememberVisitedCommand(path: string): void {
  if (path === '/home' || !commands.value.some((command) => command.path === path)) return
  recentPaths.value = mergeRecentCommand(recentPaths.value, path)
  writeJson(recentStorageKey, recentPaths.value)
}
</script>

<style scoped>
.command-trigger {
  position: fixed;
  top: 12px;
  right: 24px;
  z-index: 20;
}

:global(.command-modal) {
  width: min(680px, calc(100vw - 32px));
}

.command-results {
  display: grid;
  gap: 4px;
  margin-top: 12px;
  max-height: 430px;
  overflow-y: auto;
}

.command-row {
  align-items: center;
  background: transparent;
  border: 0;
  border-radius: 8px;
  color: inherit;
  cursor: pointer;
  display: flex;
  justify-content: space-between;
  padding: 10px 12px;
  text-align: left;
  width: 100%;
}

.command-row:hover,
.command-row.active {
  background: rgba(24, 160, 88, 0.13);
}

.command-copy {
  display: grid;
  gap: 2px;
}

.command-copy small {
  opacity: 0.65;
}

.command-empty {
  padding: 40px 0;
}
</style>
