<template>
  <n-space vertical size="large">
    <n-card>
      <n-flex justify="space-between" align="center">
        <div>
          <n-h2 style="margin: 0">ECR publication workflow</n-h2>
          <n-text depth="3">
            Review a bounded PDF snapshot, approve the exact JIRA plan, then publish through a
            fenced durable job.
          </n-text>
        </div>
        <n-button :loading="loadingList" @click="loadWorkflows">Refresh</n-button>
      </n-flex>
    </n-card>

    <n-alert v-if="errorMessage" type="error" closable @close="errorMessage = ''">
      {{ errorMessage }}
    </n-alert>
    <n-alert v-if="catalog.status === 'error'" type="error" :bordered="false">
      The project catalog is unavailable, so AW Center cannot safely authorize a new ECR review.
      <template #action>
        <n-button text type="primary" @click="loadProjects">Retry</n-button>
      </template>
    </n-alert>

    <n-grid cols="1 980:2" x-gap="16" y-gap="16">
      <n-grid-item>
        <n-card title="Start a reviewed workflow" size="small">
          <n-form label-placement="top" @submit.prevent="createWorkflow">
            <n-form-item label="ECR PDF">
              <input
                ref="fileInput"
                class="file-input"
                type="file"
                accept=".pdf,application/pdf"
                @change="selectPdf"
              />
            </n-form-item>
            <n-form-item label="Governed projects">
              <n-select
                v-model:value="selectedProjectSlugs"
                :options="projectOptions"
                :loading="catalog.status === 'loading'"
                multiple
                filterable
                placeholder="Select every project affected by this ECR"
              />
            </n-form-item>
            <n-alert v-if="catalog.status === 'ready' && !projectOptions.length" type="warning">
              No project grants the DCC operator role required to create an ECR workflow.
            </n-alert>
            <n-space justify="end">
              <n-button
                attr-type="submit"
                type="primary"
                :loading="creating"
                :disabled="!canCreate"
              >
                Review PDF snapshot
              </n-button>
            </n-space>
          </n-form>
        </n-card>

        <n-card title="My ECR workflows" size="small" class="workflow-list">
          <n-empty
            v-if="!loadingList && !workflows.length"
            description="No ECR reviews have been created yet."
          />
          <n-list v-else bordered>
            <n-list-item v-for="workflow in workflows" :key="workflow.id">
              <n-thing :title="workflow.snapshot.ecr_number" :description="workflow.snapshot.title">
                <template #header-extra>
                  <n-tag :type="statusType(workflow.status)">
                    {{ statusLabel(workflow.status) }}
                  </n-tag>
                </template>
                <n-text depth="3">
                  {{ workflow.project_slugs.join(', ') }} · Updated
                  {{ formatDate(workflow.updated_at) }}
                </n-text>
                <template #action>
                  <n-button
                    size="small"
                    :type="selectedWorkflow?.id === workflow.id ? 'primary' : 'default'"
                    @click="selectWorkflow(workflow.id)"
                  >
                    Review
                  </n-button>
                </template>
              </n-thing>
            </n-list-item>
          </n-list>
          <n-pagination
            v-if="totalWorkflows > pageSize"
            v-model:page="currentPage"
            :page-size="pageSize"
            :item-count="totalWorkflows"
            @update:page="loadWorkflows"
          />
        </n-card>
      </n-grid-item>

      <n-grid-item>
        <n-card v-if="loadingDetail" size="small">
          <n-skeleton text :repeat="8" />
        </n-card>
        <n-empty
          v-else-if="!selectedWorkflow"
          description="Select an ECR workflow to review its immutable snapshot."
        />
        <n-space v-else vertical size="large">
          <n-card size="small" :title="selectedWorkflow.snapshot.ecr_number">
            <template #header-extra>
              <n-flex align="center">
                <n-tag :type="statusType(selectedWorkflow.status)">
                  {{ statusLabel(selectedWorkflow.status) }}
                </n-tag>
                <n-text depth="3">Version {{ selectedWorkflow.version }}</n-text>
              </n-flex>
            </template>
            <n-descriptions label-placement="top" bordered :column="isNarrow ? 1 : 2">
              <n-descriptions-item
                v-for="field in snapshotFields"
                :key="field.key"
                :label="field.label"
                :span="field.wide && !isNarrow ? 2 : 1"
              >
                {{ selectedWorkflow.snapshot[field.key] || '—' }}
              </n-descriptions-item>
            </n-descriptions>
          </n-card>

          <n-alert
            v-if="selectedWorkflow.status === 'reconciliation_required'"
            type="error"
            :bordered="false"
          >
            The previous external write has an uncertain outcome. Automatic retry is disabled.
            Reconcile JIRA first, then use the explicit Resume action if the server permits it.
          </n-alert>
          <n-alert
            v-if="selectedWorkflow.publication.last_error"
            type="error"
            :title="selectedWorkflow.publication.last_error.code"
          >
            {{ selectedWorkflow.publication.last_error.detail }}
          </n-alert>
          <n-alert v-if="selectedWorkflow.status === 'published'" type="success">
            Published as {{ selectedWorkflow.publication.jira_issue_key }}. Attachment
            {{ selectedWorkflow.publication.attachment_confirmed ? 'confirmed' : 'not confirmed' }};
            {{ selectedWorkflow.publication.subtasks_confirmed }}/{{
              selectedWorkflow.publication.subtasks_total
            }}
            subtasks confirmed.
          </n-alert>

          <n-card title="Approval plan" size="small">
            <n-form label-placement="top" :disabled="!selectedWorkflow.allowed_actions.approve">
              <n-form-item label="JIRA project key">
                <n-input
                  v-model:value="approvalForm.project_key"
                  maxlength="20"
                  placeholder="AWC"
                />
              </n-form-item>
              <n-divider>Bounded subtasks</n-divider>
              <n-empty
                v-if="!approvalForm.subtasks.length"
                description="No subtasks will be created."
              />
              <n-card
                v-for="(subtask, index) in approvalForm.subtasks"
                :key="index"
                size="small"
                :title="'Subtask ' + (index + 1)"
                class="subtask-card"
              >
                <template #header-extra>
                  <n-button
                    text
                    type="error"
                    :disabled="!selectedWorkflow.allowed_actions.approve"
                    @click="removeSubtask(index)"
                  >
                    Remove
                  </n-button>
                </template>
                <n-form-item label="Summary">
                  <n-input v-model:value="subtask.summary" maxlength="255" show-count />
                </n-form-item>
                <n-form-item label="Description">
                  <n-input
                    v-model:value="subtask.description"
                    type="textarea"
                    maxlength="5000"
                    :autosize="{ minRows: 2, maxRows: 5 }"
                  />
                </n-form-item>
                <n-grid cols="1 640:3" x-gap="12">
                  <n-form-item-gi label="Assignee">
                    <n-input v-model:value="subtask.assignee" maxlength="100" />
                  </n-form-item-gi>
                  <n-form-item-gi label="Priority">
                    <n-input v-model:value="subtask.priority" maxlength="50" />
                  </n-form-item-gi>
                  <n-form-item-gi label="Due date">
                    <n-input
                      v-model:value="subtask.due_date"
                      maxlength="10"
                      placeholder="YYYY-MM-DD"
                    />
                  </n-form-item-gi>
                </n-grid>
              </n-card>
              <n-button
                v-if="selectedWorkflow.allowed_actions.approve"
                secondary
                :disabled="approvalForm.subtasks.length >= maxSubtasks"
                @click="addSubtask"
              >
                Add subtask
              </n-button>
            </n-form>
            <JiraDraftPreflightPanel
              v-if="selectedWorkflow.allowed_actions.approve"
              :connected="dccStore.isJiraConnected"
              :busy="acting"
              :dirty="preflightDirty"
              :locked="false"
              :result="preflightResult"
              :extra-fields="approvalForm.extra_fields"
              @check="checkEcrPreflight"
              @update-field="updateEcrField"
            />
            <template #action>
              <n-space justify="end">
                <n-popconfirm
                  v-if="selectedWorkflow.allowed_actions.reject"
                  @positive-click="rejectWorkflow"
                >
                  <template #trigger>
                    <n-button type="warning" :loading="acting">Reject review</n-button>
                  </template>
                  Reject this exact reviewed version?
                </n-popconfirm>
                <n-button
                  v-if="selectedWorkflow.allowed_actions.approve"
                  type="primary"
                  :loading="acting"
                  :disabled="!canApprove"
                  @click="approveWorkflow"
                >
                  Approve publication plan
                </n-button>
              </n-space>
            </template>
          </n-card>

          <n-card title="Publication" size="small">
            <n-space vertical>
              <n-alert v-if="requiresJiraConnection && !dccStore.isJiraConnected" type="warning">
                Connect your short-lived JIRA session before publishing or resuming.
                <template #action>
                  <n-button text type="primary" @click="router.push({ name: 'jira' })">
                    Open JIRA connection
                  </n-button>
                </template>
              </n-alert>
              <n-progress
                v-if="selectedWorkflow.status === 'publishing'"
                type="line"
                processing
                :percentage="publicationProgress"
              />
              <n-text v-if="selectedWorkflow.publication.job_status">
                Durable job status:
                {{ selectedWorkflow.publication.job_status.replaceAll('_', ' ') }}
              </n-text>
              <n-space justify="end">
                <n-button
                  v-if="selectedWorkflow.publication.job_id"
                  @click="openJobCenter(selectedWorkflow.publication.job_id)"
                >
                  Open Job Center
                </n-button>
                <n-button
                  v-if="selectedWorkflow.allowed_actions.cancel"
                  type="warning"
                  :loading="acting"
                  @click="cancelPublication"
                >
                  Cancel publication
                </n-button>
                <n-popconfirm
                  v-if="selectedWorkflow.allowed_actions.publish"
                  @positive-click="publishWorkflow"
                >
                  <template #trigger>
                    <n-button type="error" :loading="acting" :disabled="!dccStore.isJiraConnected">
                      Publish approved ECR
                    </n-button>
                  </template>
                  This starts external JIRA writes for the approved version. Continue?
                </n-popconfirm>
                <n-popconfirm
                  v-if="selectedWorkflow.allowed_actions.resume"
                  @positive-click="resumeWorkflow"
                >
                  <template #trigger>
                    <n-button type="error" :loading="acting" :disabled="!dccStore.isJiraConnected">
                      Resume publication
                    </n-button>
                  </template>
                  Confirm reconciliation is complete and start a new durable attempt?
                </n-popconfirm>
              </n-space>
            </n-space>
          </n-card>

          <n-card v-if="selectedWorkflow.events?.length" title="Audit history" size="small">
            <n-timeline>
              <n-timeline-item
                v-for="event in selectedWorkflow.events"
                :key="[event.type, event.version, event.created_at].join(':')"
                :title="event.type.replaceAll('_', ' ')"
                :content="'Version ' + event.version"
                :time="formatDate(event.created_at)"
              />
            </n-timeline>
          </n-card>
        </n-space>
      </n-grid-item>
    </n-grid>
  </n-space>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { formatApiError, getApiErrorCode } from '@/shared/api/apiError'
import {
  approveEcrWorkflow,
  createEcrWorkflow,
  fetchEcrWorkflow,
  fetchEcrWorkflows,
  preflightEcrWorkflow,
  publishEcrWorkflow,
  rejectEcrWorkflow,
  resumeEcrWorkflow,
  type EcrSnapshot,
  type EcrSubtask,
  type EcrApprovalInput,
  type EcrWorkflow,
  type EcrWorkflowStatus
} from '@/features/dcc/api/ecrWorkflows'
import type { JiraIssueDraftPreflight } from '@/features/dcc/api/jiraIssueDrafts'
import type { JiraFieldValue } from '@/features/dcc/models/jira'
import JiraDraftPreflightPanel from '@/features/jobs/components/JiraDraftPreflightPanel.vue'
import { cancelJob } from '@/features/jobs/api/jobs'
import { useDccStore } from '@/features/dcc/stores/dcc'
import { useProjectCatalogStore } from '@/features/projects/stores/projectCatalog'
import { useMediaQuery } from '@/shared/composables/mediaQuery'

const route = useRoute()
const router = useRouter()
const catalog = useProjectCatalogStore()
const dccStore = useDccStore()
const isNarrow = useMediaQuery('(max-width: 640px)')
const workflows = ref<EcrWorkflow[]>([])
const selectedWorkflow = ref<EcrWorkflow | null>(null)
const selectedPdf = ref<File | null>(null)
const selectedProjectSlugs = ref<string[]>([])
const fileInput = ref<HTMLInputElement | null>(null)
const totalWorkflows = ref(0)
const currentPage = ref(1)
const pageSize = 10
const loadingList = ref(false)
const loadingDetail = ref(false)
const creating = ref(false)
const acting = ref(false)
const errorMessage = ref('')
const createIdempotencyKey = ref('')
const actionIdempotencyKeys = new Map<string, string>()
const preflightResult = ref<JiraIssueDraftPreflight | null>(null)
const preflightFingerprint = ref('')
const maxSubtasks = 20
let refreshTimer: number | undefined

const approvalForm = reactive({
  project_key: '',
  extra_fields: {} as Record<string, JiraFieldValue>,
  subtasks: [] as EcrSubtask[]
})

const snapshotFields: ReadonlyArray<{
  key: keyof EcrSnapshot
  label: string
  wide?: boolean
}> = [
  { key: 'title', label: 'Title', wide: true },
  { key: 'project', label: 'Source project' },
  { key: 'change_class', label: 'Change class' },
  { key: 'change_type', label: 'Change type' },
  { key: 'effectivity', label: 'Effectivity' },
  { key: 'track_type', label: 'Track type' },
  { key: 'record_of_change', label: 'Record of change', wide: true },
  { key: 'requestor', label: 'Requestor' },
  { key: 'originator', label: 'Originator' },
  { key: 'ata', label: 'ATA' },
  { key: 'subata', label: 'Sub-ATA' },
  { key: 'initiator', label: 'Initiator' },
  { key: 'impacted_groups', label: 'Impacted groups' },
  { key: 'justification', label: 'Justification', wide: true },
  { key: 'proposed_solution', label: 'Proposed solution', wide: true },
  {
    key: 'nonimplementation_consequence',
    label: 'Consequence of non-implementation',
    wide: true
  }
]

const projectOptions = computed(() =>
  catalog.dccProjects
    .filter((project) => catalog.hasDccRole(project.slug, 'operator'))
    .map((project) => ({ label: project.name, value: project.slug }))
)
const canCreate = computed(
  () =>
    Boolean(selectedPdf.value) &&
    selectedProjectSlugs.value.length > 0 &&
    catalog.status === 'ready' &&
    !creating.value
)
const canApprove = computed(
  () =>
    Boolean(approvalForm.project_key.trim()) &&
    approvalForm.subtasks.every((subtask) => Boolean(subtask.summary.trim())) &&
    Boolean(preflightResult.value?.ready) &&
    !preflightDirty.value &&
    !acting.value
)
const preflightDirty = computed(
  () => Boolean(preflightResult.value) && preflightFingerprint.value !== approvalFingerprint()
)
const requiresJiraConnection = computed(() =>
  Boolean(
    selectedWorkflow.value?.allowed_actions.publish ||
    selectedWorkflow.value?.allowed_actions.resume
  )
)
const publicationProgress = computed(() => {
  if (!selectedWorkflow.value) return 0
  const publication = selectedWorkflow.value.publication
  const completedUnits = Number(publication.attachment_confirmed) + publication.subtasks_confirmed
  const totalUnits = 1 + publication.subtasks_total
  return totalUnits ? Math.round((completedUnits / totalUnits) * 100) : 0
})

onMounted(initialize)
onBeforeUnmount(stopRefresh)

async function initialize(): Promise<void> {
  await Promise.allSettled([loadProjects(), loadWorkflows(), refreshJiraConnection()])
  const linkedWorkflow = route.query.ecr_workflow
  if (typeof linkedWorkflow === 'string') await selectWorkflow(linkedWorkflow, false)
}

async function loadProjects(): Promise<void> {
  try {
    await catalog.load(true)
  } catch {
    // The store exposes a fail-closed error state and the UI offers an explicit retry.
  }
}

async function refreshJiraConnection(): Promise<void> {
  try {
    await dccStore.fetchJiraConnection()
  } catch {
    // Connection state remains disconnected; publication controls stay disabled.
  }
}

async function loadWorkflows(): Promise<void> {
  loadingList.value = true
  try {
    const page = await fetchEcrWorkflows(currentPage.value, pageSize)
    workflows.value = page.results
    totalWorkflows.value = page.count
    errorMessage.value = ''
  } catch (error) {
    errorMessage.value = formatApiError(error)
  } finally {
    loadingList.value = false
  }
}

function selectPdf(event: Event): void {
  const input = event.target as HTMLInputElement
  selectedPdf.value = input.files?.item(0) || null
  createIdempotencyKey.value = ''
}

async function createWorkflow(): Promise<void> {
  if (!canCreate.value || !selectedPdf.value) return
  creating.value = true
  errorMessage.value = ''
  if (!createIdempotencyKey.value) createIdempotencyKey.value = crypto.randomUUID()
  try {
    const workflow = await createEcrWorkflow(
      selectedPdf.value,
      selectedProjectSlugs.value,
      createIdempotencyKey.value
    )
    createIdempotencyKey.value = ''
    selectedPdf.value = null
    if (fileInput.value) fileInput.value.value = ''
    await loadWorkflows()
    await selectWorkflow(workflow.id)
    window.$message.success('The immutable ECR snapshot is ready for review.')
  } catch (error) {
    errorMessage.value = formatApiError(error)
  } finally {
    creating.value = false
  }
}

async function selectWorkflow(workflowId: string, updateUrl = true): Promise<void> {
  loadingDetail.value = true
  stopRefresh()
  try {
    setSelectedWorkflow(await fetchEcrWorkflow(workflowId))
    if (updateUrl) {
      await router.replace({ query: { ...route.query, ecr_workflow: workflowId } })
    }
    errorMessage.value = ''
  } catch (error) {
    errorMessage.value = formatApiError(error)
  } finally {
    loadingDetail.value = false
    scheduleRefresh()
  }
}

function setSelectedWorkflow(workflow: EcrWorkflow): void {
  selectedWorkflow.value = workflow
  approvalForm.project_key = workflow.approval.project_key
  approvalForm.extra_fields = { ...workflow.approval.extra_fields }
  approvalForm.subtasks = workflow.approval.subtasks.map((subtask) => ({ ...subtask }))
  preflightResult.value = null
  preflightFingerprint.value = ''
}

function addSubtask(): void {
  if (approvalForm.subtasks.length >= maxSubtasks) return
  approvalForm.subtasks.push(emptySubtask())
}

function removeSubtask(index: number): void {
  approvalForm.subtasks.splice(index, 1)
}

async function approveWorkflow(): Promise<void> {
  if (!selectedWorkflow.value || !canApprove.value) return
  await runWorkflowAction(() => approveEcrWorkflow(selectedWorkflow.value!, approvalPayload()))
}

async function checkEcrPreflight(): Promise<void> {
  if (!selectedWorkflow.value || !approvalForm.project_key.trim()) return
  acting.value = true
  errorMessage.value = ''
  try {
    preflightResult.value = await preflightEcrWorkflow(selectedWorkflow.value, approvalPayload())
    preflightFingerprint.value = approvalFingerprint()
  } catch (error) {
    errorMessage.value = formatApiError(error)
  } finally {
    acting.value = false
  }
}

function updateEcrField(identifier: string, value: JiraFieldValue): void {
  if (value === null || value === '' || (Array.isArray(value) && !value.length)) {
    delete approvalForm.extra_fields[identifier]
  } else {
    approvalForm.extra_fields[identifier] = value
  }
}

async function rejectWorkflow(): Promise<void> {
  if (!selectedWorkflow.value) return
  await runWorkflowAction(() => rejectEcrWorkflow(selectedWorkflow.value!))
}

async function publishWorkflow(): Promise<void> {
  if (!selectedWorkflow.value) return
  const workflow = selectedWorkflow.value
  await runWorkflowAction(() =>
    publishEcrWorkflow(workflow, idempotencyKeyFor(workflow, 'publish'))
  )
}

async function resumeWorkflow(): Promise<void> {
  if (!selectedWorkflow.value) return
  const workflow = selectedWorkflow.value
  await runWorkflowAction(() => resumeEcrWorkflow(workflow, idempotencyKeyFor(workflow, 'resume')))
}

async function cancelPublication(): Promise<void> {
  const jobId = selectedWorkflow.value?.publication.job_id
  if (!jobId) return
  acting.value = true
  errorMessage.value = ''
  try {
    await cancelJob(jobId)
    await refreshSelectedWorkflow()
    window.$message.success('Publication cancellation requested.')
  } catch (error) {
    await handleActionError(error)
  } finally {
    acting.value = false
  }
}

async function runWorkflowAction(action: () => Promise<EcrWorkflow>): Promise<void> {
  acting.value = true
  errorMessage.value = ''
  try {
    setSelectedWorkflow(await action())
    await Promise.all([loadWorkflows(), refreshSelectedWorkflow()])
  } catch (error) {
    await handleActionError(error)
  } finally {
    acting.value = false
  }
}

async function handleActionError(error: unknown): Promise<void> {
  const code = getApiErrorCode(error)
  if (code === 'ECR_VERSION_CONFLICT') {
    await refreshSelectedWorkflow()
    errorMessage.value = 'The workflow changed. The latest reviewed version has been loaded.'
    return
  }
  if (code === 'JIRA_SESSION_REQUIRED') await refreshJiraConnection()
  errorMessage.value = formatApiError(error)
}

async function refreshSelectedWorkflow(): Promise<void> {
  const workflowId = selectedWorkflow.value?.id
  if (!workflowId) return
  stopRefresh()
  try {
    setSelectedWorkflow(await fetchEcrWorkflow(workflowId))
  } catch (error) {
    errorMessage.value = formatApiError(error)
  } finally {
    scheduleRefresh()
  }
}

function scheduleRefresh(): void {
  stopRefresh()
  if (selectedWorkflow.value?.status === 'publishing') {
    refreshTimer = window.setTimeout(refreshSelectedWorkflow, 2000)
  }
}

function stopRefresh(): void {
  if (refreshTimer) window.clearTimeout(refreshTimer)
  refreshTimer = undefined
}

function idempotencyKeyFor(workflow: EcrWorkflow, action: 'publish' | 'resume'): string {
  const key = [workflow.id, workflow.version, action].join(':')
  let idempotencyKey = actionIdempotencyKeys.get(key)
  if (!idempotencyKey) {
    idempotencyKey = crypto.randomUUID()
    actionIdempotencyKeys.set(key, idempotencyKey)
  }
  return idempotencyKey
}

function normalizeSubtask(subtask: EcrSubtask): EcrSubtask {
  return {
    summary: subtask.summary.trim(),
    description: subtask.description.trim(),
    assignee: subtask.assignee.trim(),
    priority: subtask.priority.trim(),
    due_date: subtask.due_date?.trim() || null
  }
}

function approvalPayload(): EcrApprovalInput {
  return {
    project_key: approvalForm.project_key.trim(),
    extra_fields: { ...approvalForm.extra_fields },
    subtasks: approvalForm.subtasks.map(normalizeSubtask)
  }
}

function approvalFingerprint(): string {
  return JSON.stringify(approvalPayload())
}

function emptySubtask(): EcrSubtask {
  return { summary: '', description: '', assignee: '', priority: '', due_date: null }
}

function openJobCenter(jobId: string): void {
  void router.push({ name: 'jobs', query: { job: jobId } })
}

function formatDate(value: string): string {
  return new Intl.DateTimeFormat(undefined, { dateStyle: 'short', timeStyle: 'short' }).format(
    new Date(value)
  )
}

function statusLabel(status: EcrWorkflowStatus): string {
  return status.replaceAll('_', ' ')
}

function statusType(
  status: EcrWorkflowStatus
): 'default' | 'info' | 'success' | 'warning' | 'error' {
  if (status === 'published') return 'success'
  if (status === 'failed' || status === 'reconciliation_required') return 'error'
  if (status === 'rejected' || status === 'cancelled') return 'warning'
  return status === 'publishing' || status === 'approved' ? 'info' : 'default'
}
</script>

<style scoped>
.file-input {
  width: 100%;
  padding: 10px;
  border: 1px dashed var(--n-border-color);
  border-radius: 6px;
}

.workflow-list,
.subtask-card {
  margin-top: 16px;
}
</style>
