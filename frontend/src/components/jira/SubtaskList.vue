<template>
  <n-tabs
    v-model:value="activeListTab"
    type="card"
    size="small"
    addable
    closable
    @add="handleTabAdd"
    @close="handleTabClose"
    @update:value="handleTabUpdate"
  >
    <template #prefix><n-h3 style="margin: 0">Subtask Lists</n-h3></template>
    <n-tab-pane v-for="(item, index) in subtaskLists" :key="index" :name="index" :tab="item.title">
      <n-space vertical>
        <n-select
          v-model:value="selectedFieldIdentifiers"
          multiple
          filterable
          clearable
          :options="fieldOptions"
          placeholder="Search and add JIRA fields as dynamic columns"
          @update:value="activateSave"
        />
        <n-dynamic-input :value="item.list" :on-create="createListItem" :on-remove="removeListItem">
          <template #create-button-default>Add subtask row</template>
          <template #default="{ value }">
            <n-grid :cols="gridColumns" x-gap="12" y-gap="8">
              <n-grid-item>
                <n-input v-model:value="value.summary" placeholder="Summary" @change="activateSave" />
              </n-grid-item>
              <n-grid-item>
                <n-search
                  v-model:value="value.assignee"
                  placeholder="Assignee"
                  :list="store.getPeople"
                  @change="activateSave"
                />
              </n-grid-item>
              <n-grid-item v-for="field in selectedFields" :key="field.id">
                <n-input
                  v-model:value="ensureFields(value)[field.id]"
                  :placeholder="field.name"
                  @change="activateSave"
                />
              </n-grid-item>
            </n-grid>
          </template>
        </n-dynamic-input>
      </n-space>
    </n-tab-pane>
    <template #suffix>
      <n-button tertiary :type="saveButton.type" :disabled="saveButton.type == 'default'" @click="saveAllList">
        <template #icon><Save24Regular /></template>
        Save
      </n-button>
    </template>
  </n-tabs>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { Save24Regular } from '@vicons/fluent'
import { useOrgsStore } from '@/stores/api'
import NSearch from '../NSearch.vue'
import { IJiraField, ISubtaskItem, ISubtaskListItem } from '@/models/jira'

const store = useOrgsStore()
const activeListTab = ref(0)
const saveButton = ref({ type: 'default' })
const subtaskLists = ref<ISubtaskListItem[]>([])
const selectedFieldIdentifiers = ref<string[]>([])

const props = defineProps<{
  list?: ISubtaskItem[]
  fields?: IJiraField[]
}>()

const emits = defineEmits<{
  'update:list': [value: ISubtaskItem[]]
  change: []
}>()

const fieldOptions = computed(() =>
  (props.fields || []).map((field) => ({ label: field.name, value: field.id }))
)
const selectedFields = computed(() =>
  (props.fields || []).filter((field) => selectedFieldIdentifiers.value.includes(field.id))
)
const gridColumns = computed(() => Math.max(2, selectedFields.value.length + 2))

function saveAllList() {
  window.$userStore.updatePreference({ jira_list: subtaskLists.value })
  saveButton.value.type = 'default'
}

function activateSave() {
  saveButton.value.type = 'warning'
  emits('change')
}

function handleTabAdd() {
  subtaskLists.value.push({ title: 'New List', list: [] })
  setActiveList(subtaskLists.value.length - 1)
  activateSave()
}

function handleTabClose(name: string | number) {
  subtaskLists.value.splice(Number(name), 1)
  setActiveList(Math.max(0, Math.min(activeListTab.value, subtaskLists.value.length - 1)))
  activateSave()
}

function handleTabUpdate(name: string | number) {
  setActiveList(Number(name))
}

function createListItem(index: number) {
  subtaskLists.value[activeListTab.value].list.splice(index, 0, { fields: {} })
  activateSave()
}

function removeListItem(index: number) {
  subtaskLists.value[activeListTab.value].list.splice(index, 1)
  activateSave()
}

function ensureFields(value: ISubtaskItem) {
  value.fields = value.fields || {}
  return value.fields
}

function setActiveList(index: number) {
  activeListTab.value = index
  localStorage.setItem('jira>activetab>sglist', index.toString())
  emits('update:list', subtaskLists.value[index]?.list || [])
}

onMounted(() => {
  subtaskLists.value = window.$userStore.getPreferences.jira_list || []
  if (subtaskLists.value.length == 0) handleTabAdd()
  const storedTab = parseInt(localStorage.getItem('jira>activetab>sglist') || '0')
  setActiveList(storedTab < subtaskLists.value.length ? storedTab : 0)
})
</script>
