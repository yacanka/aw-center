<script setup lang="ts">
import { computed } from 'vue'
import { useManagementReports } from '@/features/management-reports/composables/useManagementReports'
import ReportSummary from '@/features/management-reports/components/ReportSummary.vue'
import { isoToTurkishDateTime, formatTurkishDate } from '@/shared/utils/time'

const {
  options,
  selected,
  envelope,
  report,
  history,
  page,
  title,
  note,
  baseline,
  baselines,
  loading,
  downloading,
  error,
  initialized,
  changeScope,
  loadHistory,
  openSaved,
  compare,
  refresh,
  save,
  download
} = useManagementReports()
const projectOptions = computed(() =>
  options.value.map((item) => ({ label: item.display_name, value: item.slug }))
)
const baselineOptions = computed(() =>
  baselines.value.map((item) => ({
    label: `${item.title} · ${isoToTurkishDateTime(item.captured_at)}`,
    value: item.id
  }))
)
const canSave = computed(
  () =>
    selected.value.length > 0 &&
    title.value.trim().length > 0 &&
    title.value.length <= 120 &&
    note.value.length <= 2000 &&
    !loading.value
)
</script>

<template>
  <main class="management-reports">
    <n-flex justify="space-between" align="center">
      <div>
        <n-h1 style="margin: 0">Management Reports</n-h1>
        <n-text depth="3">Executive portfolio summary · weekly net comparison · saved PDF</n-text>
      </div>
      <n-tag :type="report?.id ? 'info' : 'default'" round>
        {{ report?.id ? 'Saved snapshot' : 'Live overview' }}
      </n-tag>
    </n-flex>

    <n-alert v-if="error" type="error" title="Report request failed" role="alert">{{
      error
    }}</n-alert>
    <n-empty
      v-if="initialized && !options.length"
      description="No authorized compliance projects are available."
    />
    <n-card v-else title="Portfolio scope" size="small">
      <n-form-item label="Projects">
        <n-select
          :value="selected"
          :options="projectOptions"
          multiple
          clearable
          placeholder="Select projects"
          :disabled="!initialized"
          @update:value="changeScope"
        />
      </n-form-item>
      <n-flex justify="space-between" align="center">
        <n-text depth="3">Only projects you can currently view are listed.</n-text>
        <n-button :disabled="!selected.length || loading" :loading="loading" @click="refresh"
          >Refresh live overview</n-button
        >
      </n-flex>
    </n-card>
    <n-empty
      v-if="initialized && options.length && !selected.length"
      description="Select at least one project to build a portfolio."
    />
    <n-spin :show="loading">
      <section v-if="envelope" class="report-content" aria-label="Executive report">
        <n-flex justify="space-between" align="center">
          <div>
            <n-h2 style="margin: 0">{{ report?.title || 'Current portfolio' }}</n-h2>
            <n-text depth="3"
              >Captured {{ isoToTurkishDateTime(envelope.report.captured_at) }} · Week of
              {{ formatTurkishDate(envelope.report.week_start) }}</n-text
            >
          </div>
          <n-button :disabled="!report?.id || loading" :loading="downloading" @click="download"
            >Download saved PDF</n-button
          >
        </n-flex>
        <ReportSummary :envelope="envelope" />
        <n-card v-if="report?.id" title="Comparison baseline" size="small">
          <n-form-item label="Older compatible saved report (from the current history page)">
            <n-select
              :value="baseline"
              :options="baselineOptions"
              clearable
              placeholder="Automatic: previous calendar week"
              @update:value="compare"
            />
          </n-form-item>
          <n-text depth="3"
            >Clear the selection to restore the previous-week baseline. Browse report history pages
            to choose other older snapshots.</n-text
          >
        </n-card>
      </section>
      <n-empty v-else-if="loading" description="Loading portfolio…" />
    </n-spin>

    <n-card v-if="initialized && selected.length" title="Save a report" size="small">
      <n-text depth="3"
        >Capture the current server data for this scope. Saved reports are private to you and cannot
        be edited.</n-text
      >
      <n-form class="capture-form" @submit.prevent="canSave && save()">
        <n-form-item label="Report title" required>
          <n-input
            v-model:value="title"
            :maxlength="120"
            show-count
            placeholder="Weekly executive review"
          />
        </n-form-item>
        <n-form-item label="Management context / decision request (optional)">
          <n-input
            v-model:value="note"
            type="textarea"
            :maxlength="2000"
            show-count
            :autosize="{ minRows: 3, maxRows: 8 }"
            placeholder="Add context and any decision you need from management."
          />
        </n-form-item>
        <n-flex justify="end">
          <n-button attr-type="submit" type="primary" :disabled="!canSave" :loading="loading"
            >Save current report</n-button
          >
        </n-flex>
      </n-form>
    </n-card>
    <n-card v-if="initialized && selected.length" title="Saved report history" size="small">
      <n-empty
        v-if="!history.results.length"
        description="No saved reports for this exact project scope."
      />
      <n-list v-else>
        <n-list-item v-for="item in history.results" :key="item.id">
          <n-flex justify="space-between" align="center" class="history-row">
            <div>
              <strong>{{ item.title }}</strong>
              <div>
                <n-text depth="3"
                  >{{ isoToTurkishDateTime(item.captured_at) }} · Week of
                  {{ formatTurkishDate(item.week_start) }}</n-text
                >
              </div>
            </div>
            <n-button :disabled="loading" @click="openSaved(item.id)">Open report</n-button>
          </n-flex>
        </n-list-item>
      </n-list>
      <n-flex v-if="history.count > 20" justify="end" style="margin-top: 16px">
        <n-pagination
          :page="page"
          :page-size="20"
          :item-count="history.count"
          :disabled="loading"
          @update:page="loadHistory"
        />
      </n-flex>
    </n-card>
  </main>
</template>

<style scoped>
.management-reports,
.report-content {
  display: flex;
  flex-direction: column;
  gap: 20px;
}
.management-reports {
  max-width: 1500px;
  margin: 0 auto;
  padding-bottom: 32px;
}
.capture-form {
  margin-top: 20px;
}
.history-row {
  width: 100%;
  gap: 12px;
}
@media (max-width: 650px) {
  .management-reports {
    gap: 14px;
    padding-top: 48px;
  }
}
</style>
