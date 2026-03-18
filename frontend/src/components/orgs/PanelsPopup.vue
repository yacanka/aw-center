<template>
  <n-modal v-model:show="showModal" preset="card" title="Panel Information" :on-after-leave="onAfterLeave"
    :style="{ width: '40%', minWidth: '400px' }">
    <template #header-extra>
      <n-button v-if="popupMode == 'view'" ghost type="warning" @click="setPopupMode('update')" size="small"
        style="margin: 10px">
        <template #icon>
          <Edit24Regular />
        </template>
      </n-button>
    </template>

    <n-form ref="formRef" :model="panel" :rules="rules">
      <n-grid :x-gap="12" :cols="12">
        <n-form-item-gi span=12 path="project" label="Project">
          <n-select v-model:value="panel.project" :options="projectOptions" placeholder="Select Project" disabled />
        </n-form-item-gi>
        <n-form-item-gi span=5 path="name" label="Name">
          <n-input v-model:value="panel.name" @keydown.enter.prevent :readonly="popupMode == 'view'" />
        </n-form-item-gi>
        <n-form-item-gi span=5 path="discipline" label="Discipline">
          <n-input v-model:value="panel.discipline" @keydown.enter.prevent :readonly="popupMode == 'view'" />
        </n-form-item-gi>
        <n-form-item-gi span=2 path="ata" label="ATA Chapter">
          <n-input v-model:value="panel.ata" placeholder="XX-XX" @keydown.enter.prevent
            :readonly="popupMode == 'view'" />
        </n-form-item-gi>
      </n-grid>
    </n-form>

    <template #action>
      <n-flex justify="center">
        <n-button v-if="popupMode == 'new'" type="success" @click="addDatabase">Add</n-button>
        <n-button v-else-if="popupMode == 'update'" type="warning" @click="updateDatabase">Update</n-button>
      </n-flex>
    </template>
  </n-modal>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { IPanel, IProject } from '@/models/orgs'
import { FormRules, NModal } from 'naive-ui';
import { Edit24Regular } from '@vicons/fluent';
import { validateForm } from '@/composables/forms';

const rules = ref<FormRules>({
  name: [
    {
      required: true,
      trigger: "blur"
    }
  ],
  discipline: [
    {
      required: true,
      trigger: "blur"
    }
  ],
  ata: [
    {
      required: true,
      trigger: "blur"
    }
  ]
})

const formRef = ref()
const showModal = ref(false);
const panel = ref<IPanel>({} as IPanel)
const popupMode = ref()
const projectOptions = ref([])

function openModal(value: IPanel, mode: string) {
  popupMode.value = mode
  const dummy = JSON.parse(JSON.stringify(value))
  panel.value = dummy
  showModal.value = true;
  projectOptions.value = window.$orgsStore.getProjects.map((project: IProject) => {
    return { label: project.name, value: project.slug }
  })
}

function closeModal() {
  showModal.value = false;
}

async function addDatabase() {
  if (!await validateForm(formRef.value)) return
  try {
    await window.$orgsStore.createPanel(panel.value)
    closeModal()
  } catch (err) {
    console.error(err)
  }
}

async function updateDatabase() {
  if (!await validateForm(formRef.value)) return
  try {
    await window.$orgsStore.updatePanel(panel.value.id, panel.value)
    closeModal()
  } catch (err) {
    console.error(err)
  }
}

function setPopupMode(mode: string) {
  popupMode.value = mode
}

function onAfterLeave() {

}

defineExpose({ openModal })

onMounted(() => {

});
</script>
