<template>
  <n-modal v-model:show="showModal" preset="card" title="Project Information" :on-after-leave="onAfterLeave"
    :style="{ width: '40%', minWidth: '400px' }">
    <template #header-extra>
      <n-button v-if="popupMode == 'view'" ghost type="warning" @click="setPopupMode('update')" size="small"
        style="margin: 10px">
        <template #icon>
          <Edit24Regular />
        </template>
      </n-button>
    </template>

    <n-form ref="formRef" :model="project" :rules="rules">
      <n-grid :x-gap="12" :cols="12">
        <n-form-item-gi span=12 path="name" label="Name">
          <n-input v-model:value="project.name" @keydown.enter.prevent :readonly="popupMode == 'view'" />
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
import { IProject } from '@/models/orgs'
import { FormRules, NModal } from 'naive-ui';
import { Edit24Regular } from '@vicons/fluent';
import { validateForm } from '@/composables/forms';

const rules = ref<FormRules>({
  name: [
    {
      required: true,
      trigger: "blur"
    }
  ]
})

const showModal = ref(false);
const project = ref<IProject>({} as IProject)
const popupMode = ref()
const formRef = ref()

function openModal(value: IProject, mode: string) {
  popupMode.value = mode
  const dummy = JSON.parse(JSON.stringify(value))
  project.value = dummy
  showModal.value = true;
}

function closeModal() {
  showModal.value = false;
}

async function addDatabase() {
  if(!await validateForm(formRef.value)) return
  window.$orgsStore.createProject(project.value)
  closeModal()
}

async function updateDatabase() {
  if(!await validateForm(formRef.value)) return
  window.$orgsStore.updateProject(project.value.id, project.value)
  closeModal()
}

function setPopupMode(mode: string) {
  popupMode.value = mode
}

function handleItemHeaderClick(value: any) {

}

function onAfterLeave() {

}

defineExpose({ openModal })

onMounted(() => {

});
</script>
