<script setup lang="ts">
import { computed, ref } from 'vue'
import { useThemeVars } from 'naive-ui'
import type { WatcherStatus } from '../api/watcher'
const props = defineProps<{ status: WatcherStatus }>()
const theme = useThemeVars()
const showOutstanding = ref(false)
const completedCount = computed(() => props.status.subtasks.filter((task) => task.completed).length)
const displayed = computed(() =>
  props.status.subtasks.filter((task) => !showOutstanding.value || !task.completed)
)
const style = computed(() => ({
  '--detail-border': theme.value.borderColor,
  '--detail-muted': theme.value.textColor2,
  '--detail-radius': theme.value.borderRadius
}))
</script>
<template>
  <div class="details" :style="style">
    <n-text strong class="issue-title">{{ status.title }}</n-text>
    <n-flex align="center"
      ><n-tag :bordered="false" :type="status.completed ? 'success' : 'warning'">{{
        status.status || 'Unknown status'
      }}</n-tag
      ><n-text>Checked {{ new Date(status.checked_at).toLocaleString() }}</n-text></n-flex
    >
    <dl class="document-fields">
      <div>
        <dt>ECD number</dt>
        <dd>{{ status.ecd_number || 'Not provided' }}</dd>
      </div>
      <div>
        <dt>Revision</dt>
        <dd>{{ status.ecd_revision || 'Not provided' }}</dd>
      </div>
      <div>
        <dt>DCC number</dt>
        <dd>{{ status.dcc_number || 'Not provided' }}</dd>
      </div>
    </dl>
    <section aria-label="Subtasks">
      <n-flex justify="space-between" align="center">
        <h3>
          Subtasks <n-text depth="2">{{ completedCount }}/{{ status.subtasks.length }}</n-text>
        </h3>
        <n-checkbox v-if="status.subtasks.length" v-model:checked="showOutstanding"
          >Outstanding only</n-checkbox
        >
      </n-flex>
      <n-empty
        v-if="!displayed.length"
        :description="showOutstanding ? 'All subtasks are complete' : 'No subtasks on this issue'"
      />
      <ul v-else class="subtask-list">
        <li v-for="task in displayed" :key="task.issue">
          <n-flex justify="space-between" align="center">
            <n-button
              text
              tag="a"
              :href="task.jira_issue_url"
              target="_blank"
              rel="noopener noreferrer"
              >{{ task.issue }}</n-button
            >
            <n-tag :type="task.completed ? 'success' : 'warning'" :bordered="false" size="small">{{
              task.status || 'Unknown'
            }}</n-tag>
          </n-flex>
          <n-text>{{ task.title }}</n-text>
        </li>
      </ul>
    </section>
  </div>
</template>
<style scoped>
.details {
  display: grid;
  gap: 24px;
}
.issue-title {
  font-size: 18px;
  line-height: 1.5;
  overflow-wrap: anywhere;
}
h3 {
  margin: 0;
  font-size: 16px;
}
.document-fields {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 16px;
  margin: 0;
  padding: 16px;
  border: 1px solid var(--detail-border);
  border-radius: var(--detail-radius);
}
dt {
  color: var(--detail-muted);
  font-size: 13px;
  margin-bottom: 4px;
}
dd {
  margin: 0;
  overflow-wrap: anywhere;
}
.subtask-list {
  list-style: none;
  padding: 0;
  margin: 16px 0 0;
  display: grid;
  gap: 12px;
}
.subtask-list li {
  border: 1px solid var(--detail-border);
  border-radius: var(--detail-radius);
  padding: 12px 16px;
  display: grid;
  gap: 4px;
  overflow-wrap: anywhere;
}
.subtask-list :deep(.n-button) {
  min-height: 44px;
}
</style>
