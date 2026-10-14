<script setup lang="ts">
import { computed, h, onMounted, onBeforeUnmount, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { NButton, NFlex, NTag, NText, type DataTableColumns, useThemeVars } from 'naive-ui'
import type { IJiraTrackedIssue } from '@/features/integrations/jira/models/records'
import { fetchJiraTrackedIssues } from '@/features/integrations/jira/api/jiraRecords'
import {
  importWatcherIssue,
  fetchWatcherStatus,
  deleteWatcherRecord,
  fetchWatcherPreferences,
  updateWatcherPreferences,
  type WatcherPreferences,
  type WatcherStatus
} from '../api/watcher'
import { getStringFilterMenuFunc } from '@/shared/components/table/valueFilterMenus'
import type { PaginationMeta } from '@/shared/services/pagination'
import { formatApiError } from '@/shared/api/apiError'
import DccReminderDialog from '../components/DccReminderDialog.vue'
import WatcherDetails from '../components/WatcherDetails.vue'
import WatcherSettings from '../components/WatcherSettings.vue'
import WatcherRecordActions from '../components/WatcherRecordActions.vue'
import WatcherStatusSummary from '../components/WatcherStatusSummary.vue'
import WatcherAssessmentDialog from '../components/WatcherAssessmentDialog.vue'
import { useProjectCatalogStore } from '@/features/projects/stores/projectCatalog'
import { hasProjectJiraRole } from '@/features/projects/models/projectRegistry'

const router = useRouter()
const watcherElement = ref<HTMLElement | null>(null)
const compactLayout = ref(true)
const filtersVisible = ref(false)
let resizeObserver: ResizeObserver | undefined
let resizeFrame = 0
onMounted(() => {
  resizeObserver = new ResizeObserver(([entry]) => {
    cancelAnimationFrame(resizeFrame)
    const compact = entry.contentRect.width <= 900
    if (compact === compactLayout.value) return
    // Swap the layout after this observation cycle to avoid resize feedback loops.
    resizeFrame = requestAnimationFrame(() => {
      compactLayout.value = compact
    })
  })
  if (watcherElement.value) resizeObserver.observe(watcherElement.value)
})
const records = ref<IJiraTrackedIssue[]>([])
const loading = ref(false)
const pageMeta = ref<PaginationMeta>({ count: 0, next: null, previous: null })
const page = ref(1)
const pageSize = ref(12)
const reminderDialog = ref<InstanceType<typeof DccReminderDialog> | null>(null)
const assessmentDialog = ref<InstanceType<typeof WatcherAssessmentDialog> | null>(null)
const projectCatalog = useProjectCatalogStore()
const canOperate = computed(
  () =>
    projectCatalog.status === 'ready' &&
    projectCatalog.jiraProjects.some((project) =>
      hasProjectJiraRole(project.roles.jira, 'operator')
    )
)
const statuses = ref<Record<string, WatcherStatus>>({})
const statusErrors = ref<Record<string, string>>({})
const syncingIds = ref<string[]>([])
const syncing = ref(false)
const filters = ref<Record<string, unknown>>({})
const issueFilter = computed({
  get: () => String(filters.value.issue || ''),
  set: (value: string) => {
    filters.value.issue = value
  }
})
const titleFilter = computed({
  get: () => String(filters.value.title || ''),
  set: (value: string) => {
    filters.value.title = value
  }
})
const preferences = ref<WatcherPreferences>({ outstanding_only: false, detail_fields: {} })
const preferencesLoading = ref(true)
let preferenceSequence = 0
let filterTimer: ReturnType<typeof setTimeout> | undefined
const listError = ref('')
const settingsVisible = ref(false)
const importVisible = ref(false)
const issueReference = ref('')
const mutationBusy = ref(false)
const mutationError = ref('')
let requestSequence = 0
let disposed = false
onBeforeUnmount(() => {
  resizeObserver?.disconnect()
  cancelAnimationFrame(resizeFrame)
  clearTimeout(filterTimer)
  disposed = true
  requestSequence++
})
const theme = useThemeVars()
const themeStyle = computed(() => ({
  '--watcher-border': theme.value.borderColor,
  '--watcher-muted': theme.value.textColor2,
  '--watcher-surface': theme.value.cardColor,
  '--watcher-radius': theme.value.borderRadius,
  '--watcher-font': theme.value.fontFamily
}))
const selectedRecord = ref<IJiraTrackedIssue | null>(null)
const detailsVisible = ref(false)
const checkedCount = computed(() => records.value.filter((row) => statuses.value[row.id]).length)
const hasFilters = computed(() => Boolean(issueFilter.value || titleFilter.value))
const syncFinished = ref(0)
const syncTotal = ref(0)
const columns = computed<DataTableColumns<IJiraTrackedIssue>>(() => [
  {
    title: 'Issue',
    key: 'issue',
    width: 160,
    filter: true,
    filterMultiple: false,
    filterOptionValue: issueFilter.value || null,
    renderFilterMenu: getStringFilterMenuFunc('issue', filters, updateFilter),
    render: (row) =>
      h('div', { class: 'issue-cell' }, [
        h(NFlex, { align: 'center', size: 8 }, () => [
          h(
            NButton,
            {
              text: true,
              type: 'primary',
              tag: 'a',
              href: row.jira_issue_url,
              target: '_blank',
              rel: 'noopener noreferrer',
              disabled: !row.jira_issue_url
            },
            () => row.issue
          )
        ]),
        h(NText, { depth: 2 }, () => row.project_slugs.map(projectName).join(' · '))
      ])
  },
  {
    title: 'Title',
    key: 'title',
    minWidth: 240,
    filter: true,
    filterMultiple: false,
    filterOptionValue: titleFilter.value || null,
    renderFilterMenu: getStringFilterMenuFunc('title', filters, updateFilter),
    render: (row) => h(NText, { strong: true, class: 'record-title' }, () => row.title)
  },
  {
    title: 'Issue status',
    key: 'issue_status',
    width: 150,
    render: (row) =>
      statuses.value[row.id]
        ? h(
            NTag,
            {
              size: 'small',
              bordered: false,
              type: statuses.value[row.id].issue_completed ? 'success' : 'warning'
            },
            () => statuses.value[row.id].status || 'Unknown status'
          )
        : h(NText, { depth: 2 }, () =>
            syncingIds.value.includes(row.id) ? 'Checking…' : 'Not checked'
          )
  },
  {
    title: 'Subtasks status',
    key: 'status',
    width: 230,
    render: (row) =>
      h(WatcherStatusSummary, {
        status: statuses.value[row.id],
        error: statusErrors.value[row.id],
        busy: syncingIds.value.includes(row.id)
      })
  },
  {
    title: 'Actions',
    key: 'actions',
    width: 280,
    render: (row) =>
      h(WatcherRecordActions, {
        record: row,
        canEdit: canEdit(row),
        busy: syncing.value || syncingIds.value.includes(row.id),
        onDetails: () => openDetails(row),
        onReminder: () => reminderDialog.value?.open(row),
        onCheck: () => syncRow(row),
        onRemove: () => remove(row)
      })
  }
])
function projectName(slug: string): string {
  return projectCatalog.projects.find((project) => project.slug === slug)?.name || slug
}
function openDetails(row: IJiraTrackedIssue): void {
  selectedRecord.value = row
  detailsVisible.value = true
  if (!statuses.value[row.id]) void syncRow(row)
}
function clearFilters(): void {
  issueFilter.value = ''
  titleFilter.value = ''
  applyFilters()
}
function canEdit(row: IJiraTrackedIssue): boolean {
  return (
    projectCatalog.status === 'ready' &&
    row.project_slugs.length > 0 &&
    row.project_slugs.every((slug) => projectCatalog.hasJiraRole(slug, 'operator'))
  )
}
async function fetchDcc(): Promise<void> {
  clearTimeout(filterTimer)
  const sequence = ++requestSequence
  loading.value = true
  listError.value = ''
  try {
    const result = await fetchJiraTrackedIssues({
      page: page.value,
      page_size: pageSize.value,
      issue: issueFilter.value.trim(),
      title: titleFilter.value.trim()
    })
    if (sequence !== requestSequence) return
    // Settings/status requests can finish after this list was read on the server.
    // Keep their newer metadata so subsequent mutations use the current version.
    for (const record of result.results) {
      const status = statuses.value[record.id]
      if (!status || status.record_version <= record.version) continue
      record.title = status.title
      record.version = status.record_version
      record.components = status.components
    }
    records.value = result.results
    pageMeta.value = result.pagination
  } catch (error) {
    if (sequence !== requestSequence) return
    records.value = []
    pageMeta.value = { count: 0, next: null, previous: null }
    listError.value = formatApiError(error)
  } finally {
    if (sequence === requestSequence) loading.value = false
  }
}
function applyFilters(): void {
  clearTimeout(filterTimer)
  page.value = 1
  void fetchDcc()
}
function handlePageUpdate(value: number): void {
  clearTimeout(filterTimer)
  page.value = value
  void fetchDcc()
}
function handlePageSizeUpdate(value: number): void {
  pageSize.value = value
  applyFilters()
}
function applyStatus(id: string, status: WatcherStatus): void {
  if (disposed) return
  const current = records.value.find((record) => record.id === id)
  const selected = selectedRecord.value?.id === id ? selectedRecord.value : null
  // A newer table mutation takes precedence over an older discovery response.
  if (
    Math.max(
      current?.version ?? 0,
      selected?.version ?? 0,
      statuses.value[id]?.record_version ?? 0
    ) > status.record_version
  )
    return
  statuses.value[id] = status
  delete statusErrors.value[id]
  for (const record of [current, selected]) {
    if (!record) continue
    record.title = status.title
    record.version = status.record_version
    record.components = status.components
  }
}
function applyPreferences(value: WatcherPreferences): void {
  if (!disposed) preferences.value = value
}
async function syncRow(row: IJiraTrackedIssue): Promise<void> {
  if (syncingIds.value.includes(row.id)) return
  syncingIds.value.push(row.id)
  delete statuses.value[row.id]
  delete statusErrors.value[row.id]
  try {
    const status = await fetchWatcherStatus(row.id)
    if (disposed) return
    applyStatus(row.id, status)
  } catch (error) {
    statusErrors.value[row.id] = formatApiError(error)
  } finally {
    syncingIds.value = syncingIds.value.filter((id) => id !== row.id)
  }
}
async function syncPage(): Promise<void> {
  if (syncing.value) return
  syncing.value = true
  const rows = [...records.value]
  syncFinished.value = 0
  syncTotal.value = rows.length
  try {
    for (const row of rows) {
      if (disposed) break
      await syncRow(row)
      syncFinished.value++
    }
  } finally {
    syncing.value = false
  }
}
function openImport(): void {
  issueReference.value = ''
  mutationError.value = ''
  importVisible.value = true
}
async function addIssue(): Promise<void> {
  if (!issueReference.value.trim() || mutationBusy.value) return
  mutationBusy.value = true
  mutationError.value = ''
  try {
    const record = await importWatcherIssue(issueReference.value.trim())
    importVisible.value = false
    issueFilter.value = ''
    titleFilter.value = ''
    page.value = 1
    await fetchDcc()
    await syncRow(record)
    window.$message.success(`${record.issue} added to Watcher.`)
  } catch (error) {
    mutationError.value = formatApiError(error)
  } finally {
    mutationBusy.value = false
  }
}
function remove(row: IJiraTrackedIssue): void {
  window.$dialog.warning({
    title: 'Remove from Watcher',
    content: `Remove ${row.issue} from your tracked records? The JIRA issue remains available.`,
    positiveText: 'Remove',
    negativeText: 'Cancel',
    onPositiveClick: async () => {
      try {
        await deleteWatcherRecord(row)
        delete statuses.value[row.id]
        delete statusErrors.value[row.id]
        if (records.value.length === 1 && page.value > 1) page.value--
        await fetchDcc()
      } catch (error) {
        window.$message.error(formatApiError(error))
        return false
      }
    }
  })
}
function updateFilter(key: string, value: unknown): void {
  filters.value[key] = value
}
watch(
  [issueFilter, titleFilter],
  () => {
    // Invalidate the previous request immediately, including during the debounce interval.
    requestSequence++
    loading.value = false
    page.value = 1
    clearTimeout(filterTimer)
    filterTimer = setTimeout(() => void fetchDcc(), 250)
  },
  { flush: 'sync' }
)
function rowProps(row: IJiraTrackedIssue) {
  return {
    onDblclick: (event: MouseEvent) => {
      if ((event.target as HTMLElement).closest('button, a, input')) return
      openDetails(row)
    }
  }
}
async function loadPreferences(): Promise<void> {
  try {
    preferences.value = await fetchWatcherPreferences()
  } catch (error) {
    window.$message.error(formatApiError(error))
  } finally {
    preferencesLoading.value = false
  }
}
async function saveOutstanding(value: boolean): Promise<void> {
  const sequence = ++preferenceSequence
  const previous = preferences.value.outstanding_only
  preferences.value.outstanding_only = value
  preferencesLoading.value = true
  try {
    const result = await updateWatcherPreferences({ outstanding_only: value })
    if (!disposed && sequence === preferenceSequence) preferences.value = result
  } catch (error) {
    if (!disposed && sequence === preferenceSequence) {
      preferences.value.outstanding_only = previous
      window.$message.error(formatApiError(error))
    }
  } finally {
    if (sequence === preferenceSequence) preferencesLoading.value = false
  }
}
onMounted(() => {
  void fetchDcc()
  void loadPreferences()
})
</script>

<template>
  <section ref="watcherElement" class="watcher" :style="themeStyle" aria-label="JIRA Watcher">
    <header class="watcher-header">
      <div>
        <h2>JIRA Watcher</h2>
        <p>Track JIRA issues and follow up on open subtasks.</p>
      </div>
      <n-flex :size="8">
        <n-button type="primary" size="large" :disabled="!canOperate" @click="openImport"
          >Add JIRA issue</n-button
        >
        <n-button size="large" @click="settingsVisible = true">Watcher settings</n-button>
      </n-flex>
    </header>
    <n-modal
      v-model:show="settingsVisible"
      preset="card"
      title="Watcher settings"
      class="app-modal app-modal--large"
    >
      <WatcherSettings
        v-if="settingsVisible"
        :on-record-synced="applyStatus"
        :on-preferences-saved="applyPreferences"
      />
    </n-modal>
    <div class="watcher-toolbar">
      <n-flex :size="8">
        <n-button :loading="syncing" :disabled="loading || !records.length" @click="syncPage"
          >Sync this page</n-button
        >
        <n-button :disabled="!canOperate" @click="assessmentDialog?.open()">Assessment</n-button>
        <n-button :disabled="!canOperate" @click="router.push({ name: 'ecrTask' })"
          >Create from ECR</n-button
        >
        <n-button
          v-if="compactLayout"
          :aria-expanded="filtersVisible"
          aria-controls="watcher-filters"
          :type="filtersVisible ? 'primary' : 'default'"
          @click="filtersVisible = !filtersVisible"
          >Filters</n-button
        >
      </n-flex>
      <span class="check-summary" role="status" aria-live="polite">{{
        syncing
          ? `Checking ${syncFinished} of ${syncTotal} issues…`
          : `${checkedCount} of ${records.length} shown issues checked`
      }}</span>
    </div>
    <n-form
      v-if="compactLayout && filtersVisible"
      id="watcher-filters"
      class="watcher-filters"
      label-placement="top"
      :show-feedback="false"
      @submit.prevent
    >
      <n-form-item label="Issue key"
        ><n-input
          v-model:value="issueFilter"
          :input-props="{ 'aria-label': 'Filter by issue key' }"
          placeholder="e.g. CHN-42"
          clearable
      /></n-form-item>
      <n-form-item label="Title"
        ><n-input
          v-model:value="titleFilter"
          :input-props="{ 'aria-label': 'Filter by title' }"
          placeholder="Search titles"
          clearable
      /></n-form-item>
    </n-form>
    <n-alert v-if="listError" type="error" role="alert" title="Could not load tracked issues">
      <n-space vertical
        ><n-text>{{ listError }}</n-text
        ><n-button @click="fetchDcc">Try again</n-button></n-space
      >
    </n-alert>
    <div class="results-heading">
      <strong>Total: {{ pageMeta.count }}.</strong
      ><n-button :disabled="!hasFilters" @click="clearFilters">Clear filters</n-button>
    </div>
    <n-spin :show="loading">
      <n-empty
        v-if="!records.length && !loading && !listError"
        class="watcher-empty"
        :description="hasFilters ? 'No issues match these filters' : 'Your watchlist is empty'"
      >
        <template #extra
          ><n-space vertical align="center"
            ><n-text>{{
              hasFilters
                ? 'Try a different issue key or title, or clear the filters.'
                : 'Add an existing JIRA issue to follow its progress here.'
            }}</n-text
            ><n-button v-if="!hasFilters" :disabled="!canOperate" @click="openImport"
              >Add your first issue</n-button
            ></n-space
          ></template
        >
      </n-empty>
      <template v-else-if="records.length">
        <div v-if="!compactLayout" class="watcher-table">
          <n-data-table
            :columns="columns"
            :data="records"
            :row-key="(row: IJiraTrackedIssue) => row.id"
            :bordered="false"
            remote
            :row-props="rowProps"
            :filter-icon-popover-props="{
              trigger: 'click',
              duration: 250,
              displayDirective: 'show'
            }"
          />
        </div>
        <div v-else class="watcher-cards">
          <article v-for="row in records" :key="row.id" class="watcher-record">
            <n-flex align="center" justify="space-between"
              ><n-button
                text
                tag="a"
                :href="row.jira_issue_url"
                target="_blank"
                rel="noopener noreferrer"
                type="primary"
                >{{ row.issue }}</n-button
              ></n-flex
            >
            <h3>{{ row.title }}</h3>
            <n-text depth="2">{{ row.project_slugs.map(projectName).join(' · ') }}</n-text>
            <n-flex align="center" :size="8">
              <n-text depth="2">Issue status</n-text>
              <n-tag
                v-if="statuses[row.id]"
                :bordered="false"
                :type="statuses[row.id].issue_completed ? 'success' : 'warning'"
                >{{ statuses[row.id].status || 'Unknown status' }}</n-tag
              >
              <n-text v-else>Not checked</n-text>
            </n-flex>
            <n-text depth="2">Subtasks status</n-text>
            <WatcherStatusSummary
              :status="statuses[row.id]"
              :error="statusErrors[row.id]"
              :busy="syncingIds.includes(row.id)"
            />
            <WatcherRecordActions
              :record="row"
              :can-edit="canEdit(row)"
              :busy="syncing || syncingIds.includes(row.id)"
              @details="openDetails(row)"
              @reminder="reminderDialog?.open(row)"
              @check="syncRow(row)"
              @remove="remove(row)"
            />
          </article>
        </div>
      </template>
    </n-spin>
    <div v-if="pageMeta.count" class="watcher-pagination">
      <n-pagination
        v-model:page="page"
        v-model:page-size="pageSize"
        :item-count="pageMeta.count"
        :page-sizes="[12, 25, 50, 100]"
        :page-slot="3"
        show-size-picker
        :disabled="loading"
        @update:page="handlePageUpdate"
        @update:page-size="handlePageSizeUpdate"
      />
    </div>
    <n-drawer v-model:show="detailsVisible" :width="620" :style="{ maxWidth: '100vw' }">
      <n-drawer-content :title="selectedRecord?.issue || 'Issue details'" closable>
        <template v-if="selectedRecord">
          <n-space vertical :size="20">
            <n-flex
              ><n-button
                :loading="syncingIds.includes(selectedRecord.id)"
                @click="syncRow(selectedRecord)"
                >Refresh status</n-button
              ><n-button
                tag="a"
                :href="selectedRecord.jira_issue_url"
                target="_blank"
                rel="noopener noreferrer"
                >Open in JIRA</n-button
              ></n-flex
            >
            <n-alert v-if="statusErrors[selectedRecord.id]" type="error" role="alert">{{
              statusErrors[selectedRecord.id]
            }}</n-alert>
            <n-spin
              v-if="syncingIds.includes(selectedRecord.id)"
              description="Loading issue details…"
            />
            <WatcherDetails
              v-else-if="statuses[selectedRecord.id]"
              :key="selectedRecord.id"
              :status="statuses[selectedRecord.id]"
              :preferences="preferences"
              :preferences-loading="preferencesLoading"
              @outstanding="saveOutstanding"
            />
          </n-space>
        </template>
        <template #footer
          ><n-button @click="detailsVisible = false">Close details</n-button></template
        >
      </n-drawer-content>
    </n-drawer>
    <DccReminderDialog ref="reminderDialog" />
    <WatcherAssessmentDialog ref="assessmentDialog" />
    <n-modal
      v-model:show="importVisible"
      preset="dialog"
      title="Add JIRA issue"
      :mask-closable="!mutationBusy"
      :closable="!mutationBusy"
      :close-on-esc="!mutationBusy"
    >
      <n-p>Track an existing parent issue. Its title and projects are filled from JIRA.</n-p>
      <n-form-item label="JIRA issue URL or key"
        ><n-input
          v-model:value="issueReference"
          :maxlength="2048"
          :disabled="mutationBusy"
          placeholder="Paste a JIRA browse link or enter CHN-42"
          :input-props="{ 'aria-label': 'JIRA issue URL or key' }"
          @keyup.enter="addIssue"
      /></n-form-item>
      <n-alert v-if="mutationError" type="error" role="alert">{{ mutationError }}</n-alert>
      <template #action
        ><n-button :disabled="mutationBusy" @click="importVisible = false">Cancel</n-button
        ><n-button
          type="primary"
          :loading="mutationBusy"
          :disabled="!issueReference.trim()"
          @click="addIssue"
          >Add issue</n-button
        ></template
      >
    </n-modal>
  </section>
</template>

<style scoped>
.watcher {
  container-type: inline-size;
  display: grid;
  gap: 20px;
  min-width: 0;
  font-family: var(--watcher-font);
}
.watcher-header,
.watcher-toolbar,
.results-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 16px;
}
h2 {
  margin: 0;
  font-size: 24px;
  font-weight: 600;
}
.watcher-header p {
  margin: 6px 0 0;
  color: var(--watcher-muted);
  line-height: 1.6;
}
.watcher-header {
  padding: 8px 0;
}
.check-summary,
.results-heading span {
  color: var(--watcher-muted);
}
.watcher-filters {
  display: grid;
  grid-template-columns: minmax(130px, 1fr) minmax(180px, 2fr);
  gap: 12px;
  align-items: end;
  padding: 16px;
  border: 1px solid var(--watcher-border);
  border-radius: var(--watcher-radius);
  background: var(--watcher-surface);
}
.watcher-filters :deep(.n-form-item) {
  min-width: 0;
}
.watcher-toolbar :deep(.n-button) {
  min-height: 40px;
}
.results-heading {
  font-size: 13px;
}
.watcher :deep(.issue-cell) {
  display: grid;
  gap: 6px;
  padding: 4px 0;
}
.watcher :deep(.record-title) {
  overflow-wrap: anywhere;
  font-size: 15px;
  line-height: 1.5;
}
.watcher-cards {
  display: grid;
  gap: 12px;
}
.watcher-record {
  display: grid;
  gap: 12px;
  min-width: 0;
  padding: 16px;
  border: 1px solid var(--watcher-border);
  border-radius: var(--watcher-radius);
  background: var(--watcher-surface);
}
.watcher-record h3 {
  margin: 0;
  font-size: 16px;
  line-height: 1.5;
  overflow-wrap: anywhere;
}
.watcher-record > :deep(.n-flex .n-button) {
  min-height: 44px;
}
.watcher-pagination {
  display: flex;
  justify-content: end;
  overflow-x: auto;
  padding: 8px 0;
}
.watcher-empty {
  padding: 40px 16px;
  text-align: center;
}
@container (max-width: 900px) {
  .watcher-filters {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
@container (max-width: 480px) {
  .watcher-header > .n-button {
    width: 100%;
  }
  .watcher-filters {
    grid-template-columns: minmax(0, 1fr);
  }
  .watcher-toolbar :deep(.n-button) {
    min-height: 44px;
  }
  .watcher-pagination {
    justify-content: start;
  }
}
</style>
