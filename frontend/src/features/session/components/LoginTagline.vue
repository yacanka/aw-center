<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useThemeVars } from 'naive-ui'

const messages = [
  'Less routine. More room for your expertise.',
  'Bring your projects, documents and next steps together.',
  'Turn repetitive tasks into repeatable workflows.',
  'Keep compliance documents moving from draft to review.',
  'Give every document a place. Give every change a history.',
  'From spreadsheet to cover pages, without the busywork.',
  'Create project documents with a consistent starting point.',
  'Make document reviews part of the flow.',
  'Keep project responsibilities clear and work in context.',
  'Follow the progress of your work in one workspace.',
  'Turn document preparation into time for better decisions.',
  'Connect document workflows with Jira tasks.',
  'Build Jira subtasks without repeating every step.',
  'Bring engineering changes into your Jira workflow.',
  'Check DOORS module quality before the next handoff.',
  'Connect requirements with the work they support.',
  'Update Teamcenter properties through a focused workflow.',
  'Put document analysis to work for your next review.',
  'Translate Word documents as part of your working day.',
  'Take Word attachments from Outlook into your workflow.',
  'Convert media for the next step in your work.',
  'Prepare presentations for a different format.',
  'Keep document numbering connected to your project.',
  'Spend less time on repeated steps. Move meaningful work forward.'
] as const

const themeVars = useThemeVars()
const messageIndex = ref(0)
const characterCount = ref(0)
const deleting = ref(false)
const reducedMotion = ref(false)
const visibleText = computed(() => messages[messageIndex.value]!.slice(0, characterCount.value))
let timer: ReturnType<typeof setTimeout> | undefined
let motionQuery: MediaQueryList | undefined

function stop(): void {
  clearTimeout(timer)
}

function schedule(delay = 65): void {
  stop()
  if (reducedMotion.value || document.hidden) return
  timer = setTimeout(tick, delay)
}

function tick(): void {
  const message = messages[messageIndex.value]!
  if (deleting.value) {
    characterCount.value--
    if (characterCount.value === 0) {
      deleting.value = false
      messageIndex.value = (messageIndex.value + 1) % messages.length
      schedule(400)
      return
    }
    schedule(25)
    return
  }
  characterCount.value++
  if (characterCount.value === message.length) {
    deleting.value = true
    schedule(3200)
    return
  }
  schedule()
}

function syncMotion(): void {
  reducedMotion.value = motionQuery?.matches ?? false
  if (reducedMotion.value) {
    characterCount.value = messages[messageIndex.value]!.length
    deleting.value = true
  }
  schedule(3200)
}

onMounted(() => {
  motionQuery = window.matchMedia('(prefers-reduced-motion: reduce)')
  motionQuery.addEventListener('change', syncMotion)
  document.addEventListener('visibilitychange', scheduleVisibility)
  syncMotion()
})

function scheduleVisibility(): void {
  schedule(800)
}

onBeforeUnmount(() => {
  stop()
  motionQuery?.removeEventListener('change', syncMotion)
  document.removeEventListener('visibilitychange', scheduleVisibility)
})
</script>

<template>
  <div class="tagline">
    <p class="tagline-copy" aria-hidden="true">
      {{ visibleText }}<span v-if="!reducedMotion" class="cursor"></span>
    </p>
    <p class="sr-only">
      AW Center brings project documents, compliance reviews and automation into one workspace.
    </p>
  </div>
</template>

<style scoped>
.tagline {
  margin-top: 28px;
}
.tagline-copy {
  min-height: 4.95em;
  max-width: 36ch;
  margin: 0;
  color: v-bind('themeVars.textColor2');
  font-size: 18px;
  line-height: 1.65;
  overflow-wrap: break-word;
}
.cursor {
  display: inline-block;
  width: 2px;
  height: 1em;
  margin-left: 3px;
  vertical-align: -0.12em;
  background: v-bind('themeVars.primaryColor');
  animation: blink 1s step-end infinite;
}
.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
}
@keyframes blink {
  50% {
    opacity: 0;
  }
}
@media (prefers-reduced-motion: reduce) {
  .cursor {
    animation: none;
  }
}
@media (max-width: 760px) {
  .tagline {
    margin-top: 16px;
  }
  .tagline-copy {
    font-size: 16px;
  }
}
</style>
