<template>
  <n-modal v-model:show="showModal" preset="card" title="Document Information" :on-after-leave="onAfterLeave"
    :style="{ width: '60%', minWidth: '600px' }">
    <template #header-extra>
      <n-button v-if="popupMode == 'view'" ghost type="warning" @click="setPopupMode('update')" size="small"
        style="margin: 10px">
        <template #icon>
          <Edit24Regular />
        </template>
      </n-button>
    </template>
    <n-form ref="formRef" :model="ddf" :rules="rules">
      <n-grid :x-gap="12" :cols="12">
        <n-form-item-gi span=3 path="project" label="Project">
          <n-input v-model:value="ddf.project" @keydown.enter.prevent :readonly="popupMode == 'view'" />
        </n-form-item-gi>
        <n-form-item-gi span=4 path="doc_name" label="Doc Name">
          <n-input v-model:value="ddf.doc_name" @keydown.enter.prevent :readonly="popupMode == 'view'" />
        </n-form-item-gi>

        <n-form-item-gi span=2 path="doc_no" label="Doc No">
          <n-input v-model:value="ddf.doc_no" @keydown.enter.prevent :readonly="popupMode == 'view'" />
        </n-form-item-gi>
        <n-form-item-gi span=1 path="doc_issue" label="Doc Issue">
          <n-input v-model:value="ddf.doc_issue" @keydown.enter.prevent :readonly="popupMode == 'view'" />
        </n-form-item-gi>
        <n-form-item-gi span=2 path="date" label="Date">
          <n-date-picker v-model:formatted-value="ddf.date" type="date" format="dd.MM.yyyy"
          :firstDayOfWeek="0" :readonly="popupMode == 'view'" />
        </n-form-item-gi>
        <n-form-item-gi span=3 path="commentor" label="Commentor">
          <n-input v-model:value="ddf.commentor" @keydown.enter.prevent :readonly="popupMode == 'view'" />
        </n-form-item-gi>
        <n-form-item-gi span=9 path="path" label="Reference Path">
          <n-input v-model:value="ddf.path" placeholder="Path" :readonly="popupMode == 'view'"
            @click="popupMode == 'view' ? copyToClipboard() : null" @keydown.enter.prevent />
        </n-form-item-gi>
      </n-grid>
      <n-collapse @item-header-click="handleItemHeaderClick">
        <n-collapse-item title="Comments" name="comments">
          <n-dynamic-input v-model:value="ddf.comments" :disabled="popupMode == 'view'"
            :on-create="() => { return { date: new Date(Date.now()).toISOString().split('T')[0] } }"
            :on-remove="() => { console.log('Delete'); return true }">
            <template #create-button-default>
              Add Comment
            </template>
            <template #default="{ value }">
              <n-grid cols=13 x-gap=16>
                <n-grid-item span=1>
                  <n-input v-model:value="value[0]" placeholder="No" :readonly="popupMode == 'view'" />
                </n-grid-item>
                <n-grid-item span=2>
                  <n-input v-model:value="value[1]" placeholder="Relevant Section" :readonly="popupMode == 'view'" />
                </n-grid-item>

                <n-grid-item span=5>
                  <n-input type="textarea" v-model:value="value[2]" placeholder="Type Note" @keydown.enter.prevent
                    :readonly="popupMode == 'view'" />
                </n-grid-item>
                <n-grid-item span=5>
                  <n-input type="textarea" v-model:value="value[3]" placeholder="Type Note" @keydown.enter.prevent
                    :readonly="popupMode == 'view'" />
                </n-grid-item>
              </n-grid>
            </template>
          </n-dynamic-input>
        </n-collapse-item>
      </n-collapse>
    </n-form>


    <template #action>
      <n-button v-if="popupMode == 'new'" type="success" @click="addDatabase">New</n-button>
      <n-button v-else-if="popupMode == 'update'" type="warning" @click="updateDatabase">Update</n-button>
    </template>
  </n-modal>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { IDdf } from '@/models/ddf'
import { FormRules, NModal, NCollapse, NCollapseItem } from 'naive-ui';
import { Edit24Regular } from '@vicons/fluent';
import { validateForm } from '@/composables/forms';

const rules = ref<FormRules>({
  project: [
    {
      required: true,
      trigger: 'blur'
    }
  ],
  doc_name: [
    {
      required: true,
      trigger: 'blur'
    }
  ],
  doc_no: [
    {
      required: true,
      trigger: 'blur'
    }
  ],
  doc_issue: [
    {
      required: true,
      trigger: 'blur'
    }
  ],
  date: [
    {
      required: true,
      trigger: 'blur'
    }
  ],
  commentor: [
    {
      required: true,
      trigger: 'blur'
    }
  ]
})

const showModal = ref(false);
const ddf = ref<IDdf>({} as IDdf)
const popupMode = ref("")
const formRef = ref()

function openModal(value: IDdf, mode: string) {
  popupMode.value = mode
  const dummy = JSON.parse(JSON.stringify(value))
  //let dummy : IDdf = {...value}

  ddf.value = dummy
  showModal.value = true;
}

function closeModal() {
  showModal.value = false;
}

async function addDatabase() {
  if (! await validateForm(formRef.value)) return
  window.$ddfStore.createDdf(ddf.value)
}

async function updateDatabase() {
  if (! await validateForm(formRef.value)) return
  window.$ddfStore.updateDdf(ddf.value.id, ddf.value)
  closeModal()
}

function setPopupMode(mode: string) {
  popupMode.value = mode
}

async function copyToClipboard() {
  try {
    await navigator.clipboard.writeText(ddf.value.path)
    window.$message.success("Path Copied")
  } catch (err) {
    console.error(err)
  }
}

function handleItemHeaderClick(value: any) {
  console.log(value)
}

function onAfterLeave() {

}

defineExpose({ openModal })

onMounted(() => {

});
</script>
