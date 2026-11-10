<template>
  <n-card v-if="eligible" title="JIRA review bridge" size="small">
    <n-space v-if="!draft" vertical>
      <n-alert type="info" :bordered="false">
        Turn the verified private report into a reviewable JIRA Task draft. Nothing is published
        until a permitted user explicitly approves and confirms it.
      </n-alert>
      <n-select
        v-model:value="selectedProjectSlugs"
        :options="projectOptions"
        :loading="projectsLoading"
        multiple
        placeholder="Select the projects governed by this draft"
      />
      <n-button
        type="primary"
        secondary
        :loading="busy"
        :disabled="!canPrepare"
        @click="prepareDraft"
      >
        Prepare JIRA draft
      </n-button>
    </n-space>
    <n-space v-else vertical size="large">
      <n-flex justify="space-between" align="center">
        <n-tag :type="statusType">{{ draft.status }}</n-tag>
        <n-text depth="3">Version {{ draft.version }}</n-text>
      </n-flex>
      <n-alert v-if="draft.status === 'approved'" type="warning" :bordered="false">
        This version is approved. Saving an edit will require approval again.
      </n-alert>
      <n-alert v-if="draft.last_error_message" type="error" :bordered="false">
        {{ draft.last_error_message }}
        <template v-if="draft.last_error_code === 'JIRA_DRAFT_PREFLIGHT_BLOCKED'">
          Correct and save the required fields, then approve the new version.
        </template>
        <template v-else>
          You can safely retry; AW Center checks the recovery marker before creating another issue.
        </template>
      </n-alert>
      <n-alert v-if="draft.status === 'published'" type="success" :bordered="false">
        Published as
        <a
          v-if="draft.jira_issue_url"
          :href="draft.jira_issue_url"
          target="_blank"
          rel="noopener noreferrer"
        >
          {{ draft.jira_issue_key }}
        </a>
        <template v-else>{{ draft.jira_issue_key }}</template>
        .
      </n-alert>
      <n-alert v-if="publicationJob" type="info" :bordered="false">
        Publication is running as job {{ publicationJob.id }}. Follow progress in Job Center.
      </n-alert>
      <n-alert v-if="hasSaveConflict" type="warning" title="The saved draft changed">
        <n-space vertical>
          <n-text>
            Your edits are preserved. Compare version {{ draft.version }} below before continuing.
            Keeping your edits will replace its editable fields when you next save.
          </n-text>
          <n-collapse>
            <n-collapse-item
              :title="`Latest saved values (version ${draft.version})`"
              name="latest"
            >
              <n-space vertical>
                <n-text>Project: {{ draft.project_key }}</n-text>
                <n-text>Summary: {{ draft.summary }}</n-text>
                <n-input
                  :value="draft.description"
                  type="textarea"
                  readonly
                  :autosize="{ minRows: 3, maxRows: 12 }"
                  aria-label="Latest saved explainable findings"
                />
                <n-text v-for="(value, field) in draft.extra_fields" :key="field">
                  {{ field }}: {{ value }}
                </n-text>
              </n-space>
            </n-collapse-item>
          </n-collapse>
          <n-space>
            <n-button :disabled="busy" @click="reloadSavedDraft">Use latest saved values</n-button>
            <n-button :disabled="busy || !canEdit || locked" @click="keepEditsAfterConflict"
              >Keep my edits for version {{ draft.version }}</n-button
            >
          </n-space>
        </n-space>
      </n-alert>
      <n-form label-placement="top" :disabled="locked || !canEdit">
        <n-form-item label="JIRA project key">
          <n-input v-model:value="form.project_key" maxlength="20" />
        </n-form-item>
        <n-form-item label="Summary">
          <n-input v-model:value="form.summary" maxlength="255" show-count />
        </n-form-item>
        <n-form-item label="Explainable findings">
          <n-input
            v-model:value="form.description"
            type="textarea"
            maxlength="30000"
            show-count
            :autosize="{ minRows: 8, maxRows: 16 }"
          />
        </n-form-item>
      </n-form>
      <n-alert v-if="dirty" type="warning" :bordered="false">
        The form contains unsaved changes. Save them before approval or the JIRA readiness check.
      </n-alert>
      <jira-draft-preflight-panel
        v-if="canPreflight && !requiresReconciliation && draft.status !== 'published'"
        :connected="isJiraConnected"
        :busy="busy"
        :dirty="dirty"
        :locked="locked"
        :result="preflight"
        :extra-fields="form.extra_fields"
        @update-field="setExtraField"
        @check="checkPreflight"
      />
      <n-alert
        v-else-if="!canPreflight && !requiresReconciliation && draft.status !== 'published'"
        type="info"
        :bordered="false"
      >
        A user with the JIRA draft publish permission must inspect JIRA requirements and publish.
      </n-alert>
      <n-space v-if="!locked && (canEdit || canApprove)">
        <n-button
          v-if="canEdit"
          :loading="busy"
          :disabled="!dirty || hasSaveConflict"
          @click="saveDraft"
        >
          Save draft
        </n-button>
        <n-button
          v-if="canApprove && draft.status === 'draft'"
          type="primary"
          :loading="busy"
          :disabled="dirty"
          @click="approveDraft"
        >
          Approve current version
        </n-button>
      </n-space>
      <template v-if="publishable">
        <n-space v-if="canPublish" vertical>
          <template v-if="requiresReconciliation">
            <n-alert type="info" :bordered="false">
              Check the existing publication marker in JIRA. Reconciliation does not create or
              change issues.
            </n-alert>
            <n-button
              type="primary"
              :loading="busy"
              :disabled="!isJiraConnected || dirty"
              @click="publishDraft"
            >
              Reconcile publication
            </n-button>
          </template>
          <template v-else>
            <n-alert v-if="!preflight?.ready" type="warning" :bordered="false">
              Run the JIRA readiness check successfully before publication.
            </n-alert>
            <n-popconfirm @positive-click="publishDraft">
              <template #trigger>
                <n-button
                  type="error"
                  :loading="busy"
                  :disabled="!isJiraConnected || dirty || !preflight?.ready"
                >
                  Publish approved Task
                </n-button>
              </template>
              This creates an external JIRA issue. Publish the approved version?
            </n-popconfirm>
          </template>
        </n-space>
      </template>
      <n-collapse v-if="draft.events.length">
        <n-collapse-item title="Audit history" name="audit">
          <n-timeline>
            <n-timeline-item
              v-for="event in draft.events"
              :key="event.id"
              :title="event.event_type.replaceAll('_', ' ')"
              :content="`Version ${event.version}`"
              :time="formatTurkishDateTime(event.created_at, true)"
            />
          </n-timeline>
        </n-collapse-item>
      </n-collapse>
    </n-space>
  </n-card>
</template>

<script setup lang="ts">
import { formatTurkishDateTime } from '@/shared/utils/time'
import { useJiraIssueDraft } from '@/features/integrations/jira/composables/useJiraIssueDraft'
import type { Job } from '@/features/jobs/api/jobs'
import JiraDraftPreflightPanel from './JiraDraftPreflightPanel.vue'

const props = defineProps<{ job: Job }>()
const {
  draft,
  busy,
  form,
  preflight,
  eligible,
  locked,
  publishable,
  requiresReconciliation,
  canEdit,
  canApprove,
  canPreflight,
  canPublish,
  canPrepare,
  isJiraConnected,
  statusType,
  dirty,
  hasSaveConflict,
  projectOptions,
  projectsLoading,
  publicationJob,
  selectedProjectSlugs,
  prepareDraft,
  saveDraft,
  keepEditsAfterConflict,
  reloadSavedDraft,
  approveDraft,
  checkPreflight,
  setExtraField,
  publishDraft
} = useJiraIssueDraft(() => props.job)
</script>
