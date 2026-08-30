<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { QuestionCircle20Regular } from '@vicons/fluent'

interface HelpSection {
  title: string
  description: string
}

interface TabHelp {
  title: string
  purpose: string
  sections: HelpSection[]
}

const HELP_BY_TAB: Record<string, TabHelp> = {
  overview: {
    title: 'Overview',
    purpose: 'Review the document summary and use its common actions.',
    sections: [
      section('Quick actions', 'Open, edit, export, or copy the document source path.'),
      section('Document identity', 'Review Panel, ATA, references, responsible, and signatures.'),
      section('Requirements', 'See the requirements linked to this document.'),
      section('Notes', 'Read supporting context stored with the document.')
    ]
  },
  tracking: {
    title: 'Tracking & Alerts',
    purpose: 'Monitor revisions and manage document notification delivery.',
    sections: [
      section('DocProof revision', 'Compare the recorded issue with the latest DocProof issue.'),
      section('Responsible team', 'Choose which ATA contacts receive alerts.'),
      section('Automatic alerts', 'Select the document events AW Center should monitor.'),
      section('Notification policy', 'Manage project cadence, roles, retries, and escalation.'),
      section('Notification delivery', 'Send an applicable alert or download an Outlook draft.'),
      section('Delivery activity', 'Review recent delivery outcomes and policy evidence.')
    ]
  },
  ownership: {
    title: 'Ownership',
    purpose: 'Assign operational accountability for the document.',
    sections: [
      section('Owner and team', 'Select the AW Center owner and responsible group.'),
      section('Next action due', 'Record the deadline for the next expected action.')
    ]
  },
  reviews: {
    title: 'Review & Approval',
    purpose: 'Create and complete accountable decision tasks.',
    sections: [
      section('Request decision', 'Assign a review or approval task with a due date and note.'),
      section('Pending tasks', 'Approve, request changes, or cancel with recorded evidence.')
    ]
  },
  transition: {
    title: 'Transition',
    purpose: 'Record an audited lifecycle status change.',
    sections: [
      section('New status', 'Select the lifecycle state that becomes effective.'),
      section('Dates and reason', 'Record effective and next-action dates with optional context.')
    ]
  },
  activity: {
    title: 'Activity',
    purpose: 'Inspect the chronological audit trail.',
    sections: [
      section('Timeline', 'See who changed the document, what changed, and when it occurred.')
    ]
  }
}

const props = defineProps<{ tab: string; active: boolean }>()
const show = ref(false)
const help = computed(() => HELP_BY_TAB[props.tab] || HELP_BY_TAB.overview)

watch(
  () => props.active,
  (active) => {
    if (!active) show.value = false
  },
  { flush: 'sync' }
)

function section(title: string, description: string): HelpSection {
  return { title, description }
}
</script>

<template>
  <n-popover
    :show="show"
    trigger="click"
    placement="bottom-end"
    :width="320"
    @update:show="show = $event"
  >
    <template #trigger>
      <n-button quaternary circle size="small" aria-label="Help for current workspace tab">
        <template #icon><QuestionCircle20Regular /></template>
      </n-button>
    </template>
    <n-space vertical :size="10" class="context-help">
      <div>
        <n-text strong>{{ help.title }}</n-text>
        <n-text tag="p" depth="3">{{ help.purpose }}</n-text>
      </div>
      <div v-for="item in help.sections" :key="item.title" class="context-help-section">
        <n-text strong>{{ item.title }}</n-text>
        <n-text tag="p" depth="3">{{ item.description }}</n-text>
      </div>
    </n-space>
  </n-popover>
</template>

<style scoped>
.context-help p {
  margin: 2px 0 0;
}

.context-help-section {
  padding-top: 8px;
  border-top: 1px solid var(--n-border-color);
}
</style>
