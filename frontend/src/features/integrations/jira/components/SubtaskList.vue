<template>
  <n-alert v-if="contentError" type="error" title="Saved JIRA lists">
    {{ contentError }}
    <n-button v-if="!initialized" :disabled="loadingContent" @click="loadSavedLists"
      >Retry loading</n-button
    >
    <n-button v-else :disabled="saving" @click="reloadSavedLists">Reload saved lists</n-button>
  </n-alert>
  <p v-if="loadingContent" role="status">Loading saved lists…</p>
  <n-tabs
    v-model:value="activeListTab"
    type="card"
    size="small"
    :addable="initialized && !saving"
    :closable="initialized && !saving"
    @add="handleTabAdd"
    @close="handleTabClose"
    @update:value="handleTabUpdate"
  >
    <template #prefix><n-h3 style="margin: 0">Subtask Lists</n-h3></template>
    <n-tab-pane v-for="(item, index) in subtaskLists" :key="index" :name="index" :tab="item.title">
      <template #tab>
        <n-input-width
          v-if="renamingListIndex == index"
          v-model:value="listTitleDraft"
          size="tiny"
          autofocus
          @blur="commitListTitle"
          @keyup.enter="commitListTitle"
          @keyup.esc="cancelListTitleEdit"
          @click.stop
        />
        <span v-else @dblclick.stop="startListTitleEdit(index)">{{ item.title }}</span>
      </template>
      <n-space vertical>
        <div class="subtask-tools">
          <n-select
            v-model:value="selectedFieldIdentifiers"
            multiple
            filterable
            clearable
            :options="fieldOptions"
            placeholder="Search and add JIRA fields as dynamic columns"
            @update:value="handleFieldSelection"
          />
          <n-button
            class="subtask-tool-button"
            type="primary"
            ghost
            :loading="fieldLoading"
            :disabled="fieldLoadDisabled"
            @click="emits('load-fields')"
          >
            Load Fields
          </n-button>
          <div class="subtask-bulk-fields">
            <n-input v-model:value="bulkValues.summary" placeholder="Summary" clearable />
            <jira-field-input
              v-for="field in activeFields"
              :key="`bulk-${field.id}`"
              :field="field"
              :model-value="getBulkFieldValue(field.id)"
              @update:model-value="setBulkFieldValue(field.id, $event)"
            />
          </div>
          <n-button class="subtask-tool-button" type="primary" secondary @click="setBulkValues">
            Set Values
          </n-button>
        </div>
        <n-divider style="margin: 4px 0 8px" />
        <n-dynamic-input :value="item.list" :on-create="createListItem" :on-remove="removeListItem">
          <template #create-button-default>Add subtask row</template>
          <template #default="{ value }">
            <n-grid :cols="gridColumns" x-gap="12" y-gap="8">
              <n-grid-item>
                <n-input
                  v-model:value="value.summary"
                  placeholder="Summary"
                  @change="activateSave"
                />
              </n-grid-item>
              <n-grid-item v-for="field in activeFields" :key="field.id">
                <jira-field-input
                  :field="field"
                  :model-value="getFieldValue(value, field.id)"
                  @update:model-value="setFieldValue(value, field.id, $event)"
                  @change="activateSave"
                />
              </n-grid-item>
            </n-grid>
          </template>
        </n-dynamic-input>
      </n-space>
    </n-tab-pane>
    <template #suffix>
      <n-button
        tertiary
        :type="saveButton.type"
        :disabled="!initialized || loadingContent || saving || saveButton.type == 'default'"
        @click="saveAllList"
      >
        <template #icon><Save24Regular /></template>
        Save
      </n-button>
    </template>
  </n-tabs>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { NAlert, NButton } from 'naive-ui'
import { Save24Regular } from '@vicons/fluent'
import NInputWidth from '@/shared/components/NInputWidth.vue'
import JiraFieldInput from './JiraFieldInput.vue'
import type {
  IJiraField,
  ISubtaskItem,
  ISubtaskListItem,
  JiraFieldValue
} from '@/features/integrations/jira/models/jira'
import { useSessionStore } from '@/features/session/stores/session'
import { fetchSavedJiraLists, saveJiraLists } from '../api/jiraSavedLists'
import { formatApiError } from '@/shared/api/apiError'

const session = useSessionStore()
const saving = ref(false)
const loadingContent = ref(false)
const initialized = ref(false)
const contentError = ref('')
const contentVersion = ref(0)
let requestSequence = 0
let disposed = false
onBeforeUnmount(() => {
  disposed = true
  requestSequence++
})
let editVersion = 0

const activeListTab = ref(0)
const saveButton = ref<{ type: 'default' | 'warning' }>({ type: 'default' })
const subtaskLists = ref<ISubtaskListItem[]>([])
const selectedFieldIdentifiers = ref<string[]>([])
const renamingListIndex = ref<number | null>(null)
const listTitleDraft = ref('')
let titleEditOwner: number | undefined
const bulkValues = ref<ISubtaskItem>({ fields: {} })

const props = defineProps<{
  list?: ISubtaskItem[]
  fields?: IJiraField[]
  fieldLoading?: boolean
  fieldLoadDisabled?: boolean
}>()

const emits = defineEmits<{
  'update:list': [value: ISubtaskItem[]]
  change: []
  'load-fields': []
}>()

const availableFields = computed(() => mergeFields(props.fields || [], activeFields.value))
const fieldOptions = computed(() =>
  availableFields.value
    .filter((field) => field.id != 'summary')
    .map((field) => ({ label: field.name, value: field.id }))
)
const activeFields = computed(() => subtaskLists.value[activeListTab.value]?.fields || [])
const gridColumns = computed(() => Math.max(1, activeFields.value.length + 1))

watch(
  () => props.fields,
  () => syncActiveFieldsWithLoadedFields()
)

async function saveAllList() {
  if (saving.value || !initialized.value || loadingContent.value) return
  saving.value = true
  const savedVersion = editVersion
  const owner = session.getUser.id
  const sequence = requestSequence
  contentError.value = ''
  try {
    const result = await saveJiraLists({
      lists: JSON.parse(JSON.stringify(subtaskLists.value)),
      version: contentVersion.value
    })
    if (disposed || sequence !== requestSequence || owner !== session.getUser.id) return
    contentVersion.value = result.version
    if (savedVersion === editVersion) saveButton.value.type = 'default'
  } catch (error) {
    if (!disposed && sequence === requestSequence && owner === session.getUser.id)
      contentError.value = formatApiError(error)
  } finally {
    if (!disposed && sequence === requestSequence && owner === session.getUser.id)
      saving.value = false
  }
}

function activateSave() {
  editVersion += 1
  saveButton.value.type = 'warning'
  emits('change')
}

function handleFieldSelection(values: string[]) {
  const list = subtaskLists.value[activeListTab.value]
  if (!list) return
  list.fields = availableFields.value.filter((field) => values.includes(field.id))
  selectedFieldIdentifiers.value = values
  activateSave()
}

function handleTabAdd() {
  subtaskLists.value.push({ title: 'New List', list: [], fields: [] })
  setActiveList(subtaskLists.value.length - 1)
  activateSave()
}

function handleTabClose(name: string | number) {
  cancelListTitleEdit()
  subtaskLists.value.splice(Number(name), 1)
  setActiveList(Math.max(0, Math.min(activeListTab.value, subtaskLists.value.length - 1)))
  activateSave()
}

function handleTabUpdate(name: string | number) {
  cancelListTitleEdit()
  setActiveList(Number(name))
}

function startListTitleEdit(index: number) {
  titleEditOwner = session.getUser.id
  renamingListIndex.value = index
  listTitleDraft.value = subtaskLists.value[index]?.title || ''
}

function commitListTitle() {
  if (titleEditOwner !== session.getUser.id || !initialized.value) {
    cancelListTitleEdit()
    return
  }
  if (renamingListIndex.value == null) return
  const title = listTitleDraft.value.trim() || 'New List'
  subtaskLists.value[renamingListIndex.value].title = title
  cancelListTitleEdit()
  activateSave()
}

function cancelListTitleEdit() {
  renamingListIndex.value = null
  listTitleDraft.value = ''
}

function createListItem(index: number) {
  subtaskLists.value[activeListTab.value].list.splice(index, 0, { fields: {} })
  activateSave()
}

function removeListItem(index: number) {
  subtaskLists.value[activeListTab.value].list.splice(index, 1)
  activateSave()
}

function getFieldValue(value: ISubtaskItem, fieldIdentifier: string) {
  return fieldIdentifier == 'assignee'
    ? value.assignee || null
    : ensureFields(value)[fieldIdentifier]
}

function setFieldValue(value: ISubtaskItem, fieldIdentifier: string, fieldValue: JiraFieldValue) {
  if (fieldIdentifier == 'assignee') value.assignee = fieldValue ? String(fieldValue) : ''
  else ensureFields(value)[fieldIdentifier] = fieldValue
}

function getBulkFieldValue(fieldIdentifier: string) {
  return getFieldValue(bulkValues.value, fieldIdentifier)
}

function setBulkFieldValue(fieldIdentifier: string, fieldValue: JiraFieldValue) {
  setFieldValue(bulkValues.value, fieldIdentifier, fieldValue)
}

function setBulkValues() {
  const values = collectBulkValues()
  if (Object.keys(values).length == 0) return
  subtaskLists.value[activeListTab.value]?.list.forEach((item) => applyBulkValues(item, values))
  activateSave()
}

function collectBulkValues() {
  const values: Record<string, JiraFieldValue> = {}
  if (hasBulkValue(bulkValues.value.summary)) values.summary = bulkValues.value.summary || ''
  Object.entries(bulkValues.value.fields || {}).forEach(([key, value]) =>
    setBulkValue(values, key, value)
  )
  if (hasBulkValue(bulkValues.value.assignee)) values.assignee = bulkValues.value.assignee || ''
  return values
}

function setBulkValue(values: Record<string, JiraFieldValue>, key: string, value: JiraFieldValue) {
  if (hasBulkValue(value)) values[key] = value
}

function hasBulkValue(value: JiraFieldValue | undefined) {
  return value !== undefined && value !== null && String(value).trim() !== ''
}

function applyBulkValues(item: ISubtaskItem, values: Record<string, JiraFieldValue>) {
  Object.entries(values).forEach(([key, value]) => applyBulkValue(item, key, value))
}

function applyBulkValue(item: ISubtaskItem, key: string, value: JiraFieldValue) {
  if (key == 'summary') item.summary = String(value)
  else if (key == 'assignee') item.assignee = String(value)
  else ensureFields(item)[key] = Array.isArray(value) ? [...value] : value
}

function ensureFields(value: ISubtaskItem) {
  value.fields = value.fields || {}
  return value.fields
}

function setActiveList(index: number) {
  activeListTab.value = index
  bulkValues.value = { fields: {} }
  selectedFieldIdentifiers.value = activeFields.value.map((field) => field.id)
  try {
    localStorage.setItem('jira>activetab>sglist', index.toString())
  } catch {
    /* Storage is optional. */
  }
  emits('update:list', subtaskLists.value[index]?.list || [])
}

function syncActiveFieldsWithLoadedFields() {
  const list = subtaskLists.value[activeListTab.value]
  if (!list) return
  list.fields = mergeFields(props.fields || [], list.fields || []).filter((field) =>
    selectedFieldIdentifiers.value.includes(field.id)
  )
}

function mergeFields(primaryFields: IJiraField[], secondaryFields: IJiraField[]) {
  const fieldsByIdentifier = new Map<string, IJiraField>()
  secondaryFields.forEach((field) => fieldsByIdentifier.set(field.id, field))
  primaryFields.forEach((field) => fieldsByIdentifier.set(field.id, field))
  return Array.from(fieldsByIdentifier.values())
}

async function loadSavedLists() {
  const sequence = ++requestSequence
  const owner = session.getUser.id
  loadingContent.value = true
  contentError.value = ''
  try {
    const result = await fetchSavedJiraLists()
    if (disposed || sequence !== requestSequence || owner !== session.getUser.id) return
    subtaskLists.value = result.lists
    contentVersion.value = result.version
    initialized.value = true
    editVersion = 0
    saveButton.value.type = 'default'
    if (subtaskLists.value.length === 0) handleTabAdd()
    let storedTab = 0
    try {
      storedTab = parseInt(localStorage.getItem('jira>activetab>sglist') || '0')
    } catch {
      /* Storage is optional. */
    }
    setActiveList(storedTab >= 0 && storedTab < subtaskLists.value.length ? storedTab : 0)
  } catch (error) {
    if (!disposed && sequence === requestSequence && owner === session.getUser.id)
      contentError.value = formatApiError(error)
  } finally {
    if (!disposed && sequence === requestSequence && owner === session.getUser.id)
      loadingContent.value = false
  }
}

function reloadSavedLists() {
  window.$dialog.warning({
    title: 'Reload saved lists?',
    content: 'Your unsaved changes will be replaced by the saved content.',
    positiveText: 'Reload',
    negativeText: 'Keep edits',
    onPositiveClick: () => loadSavedLists()
  })
}

watch(
  () => session.getUser.id,
  () => {
    requestSequence++
    initialized.value = false
    saving.value = false
    cancelListTitleEdit()
    bulkValues.value = { fields: {} }
    selectedFieldIdentifiers.value = []
    contentError.value = ''
    subtaskLists.value = []
    emits('update:list', [])
    if (session.getUser.id) void loadSavedLists()
  }
)
onMounted(loadSavedLists)
</script>

<style scoped>
.subtask-tools {
  display: grid;
  gap: 8px 12px;
  grid-template-columns: minmax(0, 1fr) 120px;
}

.subtask-bulk-fields {
  display: grid;
  gap: 8px 12px;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
}

.subtask-tool-button {
  width: 120px;
}
</style>
