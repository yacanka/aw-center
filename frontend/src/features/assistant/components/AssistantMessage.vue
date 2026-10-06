<template>
  <article
    class="assistant-message"
    :class="{ 'user-message': message.role === 'user' }"
    :aria-label="
      catalog
        ? 'Available applications'
        : message.role === 'user'
          ? 'Your message'
          : 'Assistant response'
    "
  >
    <strong class="message-role">{{
      catalog ? 'Available applications' : message.role === 'user' ? 'You' : 'Assistant'
    }}</strong>
    <p v-if="!catalog" class="message-content">{{ message.content }}</p>
    <div v-if="applications.length" class="message-links" aria-label="Suggested applications">
      <n-button
        v-for="application in applications"
        :key="application.id"
        class="guide-button"
        block
        :aria-label="`Open ${application.title}`"
        @click="navigate(application.path)"
      >
        <span class="guide-copy"
          ><strong>{{ application.title }}</strong
          ><span>{{ application.description }}</span></span
        >
      </n-button>
    </div>
    <div v-if="sources.length" class="message-links" aria-label="Application guide sources">
      <span class="source-label">Application guides</span>
      <n-button
        v-for="source in sources"
        :key="source.id"
        class="guide-button"
        block
        :aria-label="`Open guide: ${source.title}`"
        @click="navigate(source.path)"
        >{{ source.title }}</n-button
      >
    </div>
  </article>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { useThemeVars } from 'naive-ui'
import type { AssistantMessage } from '@/features/assistant/stores/assistant'
import { resolveAssistantPath } from '@/features/assistant/models/navigation'

const props = defineProps<{ message: AssistantMessage; catalog?: boolean }>()
const router = useRouter()
const themeVars = useThemeVars()
const applications = computed(() =>
  (props.message.applications || []).filter((item) => resolveAssistantPath(item.path, router))
)
const sources = computed(() =>
  (props.message.sources || []).filter((item) => resolveAssistantPath(item.path, router))
)
function navigate(path: string): void {
  const target = resolveAssistantPath(path, router)
  if (target) void router.push(target)
}
</script>

<style scoped>
.assistant-message {
  background: v-bind('themeVars.cardColor');
  border: 1px solid v-bind('themeVars.borderColor');
  border-radius: v-bind('themeVars.borderRadius');
  color: v-bind('themeVars.textColor1');
  padding: 12px;
  min-width: 0;
}
.user-message {
  background: v-bind('themeVars.actionColor');
}
.message-role,
.source-label {
  color: v-bind('themeVars.textColor2');
}
.message-content {
  margin: 8px 0 0;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  line-height: 1.6;
}
.message-links {
  display: grid;
  gap: 8px;
  margin-top: 12px;
}
.guide-button {
  min-height: 44px;
  height: auto;
  padding: 10px 12px;
  text-align: left;
}
.guide-button :deep(.n-button__content) {
  white-space: normal;
  width: 100%;
  overflow-wrap: anywhere;
}
.guide-copy {
  display: grid;
  gap: 4px;
}
.guide-copy > span {
  color: v-bind('themeVars.textColor2');
}
.guide-button:focus-visible {
  outline: 2px solid v-bind('themeVars.primaryColor');
  outline-offset: 2px;
}
</style>
