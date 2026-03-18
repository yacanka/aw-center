<template>
  <n-modal v-model:show="showModal" preset="card" title="Document Information" centered
    :style="{ width: '60%', minWidth: '600px' }">
    <template #header-extra>
      <n-button v-if="popupMode == 'view'" ghost type="warning" @click="setPopupMode('update')" size="small"
        style="margin: 10px">
        <template #icon>
          <Edit24Regular />
        </template>
      </n-button>
    </template>
    <n-form ref="formRef" :model="compdoc" :rules="rules">
      <n-grid :x-gap="12" :cols="48">
        <n-form-item-gi span=12 path="panel" label="Panel">
          <n-select v-model:value="compdoc.panel" placeholder="Select Panel" :options="orgs.getPanelOptions"
            :disabled="popupMode == 'view'" :status="originalCompdoc.panel != compdoc.panel ? 'warning' : ''" />
        </n-form-item-gi>
        <n-form-item-gi span=4 path="ata" label="Ata">
          <n-select v-model:value="compdoc.ata" placeholder="XX-XX" :options="orgs.getAtaOptions"
            :disabled="popupMode == 'view'" :status="originalCompdoc.ata != compdoc.ata ? 'warning' : ''" />
        </n-form-item-gi>
        <n-form-item-gi span=32 path="name" label="Name">
          <n-input v-model:value="compdoc.name" @keydown.enter.prevent :readonly="popupMode == 'view'"
            :status="originalCompdoc.name != compdoc.name ? 'warning' : ''" />
        </n-form-item-gi>

        <n-form-item-gi span=12 path="signature_panel" label="Signature Panel">
          <n-select v-model:value="compdoc.signature_panel" placeholder="Select Panel" :options="orgs.getPanelOptions"
            multiple max-tag-count="responsive" :disabled="popupMode == 'view'"
            :status="!checkArrayEquals(originalCompdoc.signature_panel, compdoc.signature_panel) ? 'warning' : ''" />
        </n-form-item-gi>
        <n-form-item-gi span=8 path="cover_page_no" label="Cover Page No" :offset="1">
          <n-input v-model:value="compdoc.cover_page_no" @keydown.enter.prevent :readonly="popupMode == 'view'"
            :status="originalCompdoc.cover_page_no != compdoc.cover_page_no ? 'warning' : ''" />
        </n-form-item-gi>
        <n-form-item-gi span=3 path="cover_page_issue" label="Issue">
          <n-input v-model:value="compdoc.cover_page_issue" placeholder="X" @keydown.enter.prevent label-width="5px"
            :readonly="popupMode == 'view'"
            :status="originalCompdoc.cover_page_issue != compdoc.cover_page_issue ? 'warning' : ''" />
        </n-form-item-gi>
        <n-form-item-gi span=12 path="tech_doc_no" label="Tech Doc No" :offset="1">
          <n-input v-model:value="compdoc.tech_doc_no" @keydown.enter.prevent :readonly="popupMode == 'view'"
            :status="originalCompdoc.tech_doc_no != compdoc.tech_doc_no ? 'warning' : ''" />
        </n-form-item-gi>
        <n-form-item-gi span=3 path="tech_doc_issue" label="Issue">
          <n-input v-model:value="compdoc.tech_doc_issue" placeholder="X" @keydown.enter.prevent
            :readonly="popupMode == 'view'"
            :status="originalCompdoc.tech_doc_issue != compdoc.tech_doc_issue ? 'warning' : ''" />
        </n-form-item-gi>
        <n-form-item-gi span=3 path="delivered_tech_doc_issue" label="Delivered Issue">
          <template #label>
            <div style="width: 128px"> Delivered Issue </div>
          </template>
          <n-input v-model:value="compdoc.delivered_tech_doc_issue" placeholder="X" @keydown.enter.prevent
            :readonly="popupMode == 'view'"
            :status="originalCompdoc.delivered_tech_doc_issue != compdoc.delivered_tech_doc_issue ? 'warning' : ''" />
        </n-form-item-gi>

        <n-form-item-gi v-if="hasExtraFields" span=12 path="tech_doc_no_2" label="Tech Doc No 2" :offset="25">
          <n-input v-model:value="compdoc.tech_doc_no_2" @keydown.enter.prevent :readonly="popupMode == 'view'"
            :status="originalCompdoc.tech_doc_no_2 != compdoc.tech_doc_no_2 ? 'warning' : ''" />
        </n-form-item-gi>
        <n-form-item-gi v-if="hasExtraFields" span=3 path="tech_doc_issue_2" label="Issue 2">
          <n-input v-model:value="compdoc.tech_doc_issue_2" placeholder="X" @keydown.enter.prevent
            :readonly="popupMode == 'view'"
            :status="originalCompdoc.tech_doc_issue_2 != compdoc.tech_doc_issue_2 ? 'warning' : ''" />
        </n-form-item-gi>
        <n-form-item-gi v-if="hasExtraFields" span=3 path="delivered_tech_doc_issue_2" label="Delivered Issue 2">
          <template #label>
            <div style="width: 128px"> Delivered Issue 2</div>
          </template>
          <n-input v-model:value="compdoc.delivered_tech_doc_issue_2" placeholder="X" @keydown.enter.prevent
            :readonly="popupMode == 'view'"
            :status="originalCompdoc.delivered_tech_doc_issue_2 != compdoc.delivered_tech_doc_issue_2 ? 'warning' : ''" />
        </n-form-item-gi>

        <n-form-item-gi span=12 path="responsible" label="Responsible">
          <n-input v-model:value="compdoc.responsible" @keydown.enter.prevent :readonly="popupMode == 'view'"
            :status="originalCompdoc.responsible != compdoc.responsible ? 'warning' : ''" />
        </n-form-item-gi>
        <n-form-item-gi span=4 path="cat" label="Cat">
          <n-select v-model:value="compdoc.cat" placeholder="None" :options="catOptions" clearable
            :disabled="popupMode == 'view'" :status="originalCompdoc.cat != compdoc.cat ? 'warning' : ''" />
        </n-form-item-gi>
        <n-form-item-gi span=4 path="moc" label="MoC">
          <n-select v-model:value="compdoc.moc" placeholder="X" :options="mocOptions" clearable
            :disabled="popupMode == 'view'" :status="originalCompdoc.moc != compdoc.moc ? 'warning' : ''" />
        </n-form-item-gi>
        <n-form-item-gi span=8 path="mom_no" label="Mom No" :offset="1">
          <n-input type="textarea" rows="1" v-model:value="compdoc.mom_no" :autosize="{ minRows: 1, maxRows: 3 }"
            :readonly="popupMode == 'view'" :status="originalCompdoc.mom_no != compdoc.mom_no ? 'warning' : ''" />
        </n-form-item-gi>

        <n-form-item-gi span=48 path="requirements" label="Requirements">
          <n-dynamic-tags v-model:value="compdoc.requirements" :disabled="popupMode == 'view'" />
        </n-form-item-gi>

        <n-form-item-gi span=48 path="status_flow" label="Status Flow">
          <n-dynamic-input v-model:value="compdoc.status_flow" :disabled="popupMode == 'view'"
            :on-create="() => { return { date: getTodayEUFormat() } }"
            :on-remove="() => { console.log('Delete'); return true }">
            <template #create-button-default>
              Add status and date
            </template>
            <template #default="{ value }">
              <n-grid cols=48 x-gap=16>
                <n-grid-item span=12>
                  <n-select v-model:value="value.status" :options="statusOptions" placeholder="Select Status"
                    :disabled="popupMode == 'view'" />
                </n-grid-item>
                <n-grid-item span=8>
                  <n-date-picker v-model:formatted-value="value.date" type="date" format="dd.MM.yyyy"
                    :firstDayOfWeek="0" :disabled="popupMode == 'view'" />
                </n-grid-item>
                <n-grid-item span=28>
                  <n-input v-model:value="value.note" placeholder="Type note" @keydown.enter.prevent
                    :readonly="popupMode == 'view'" />
                </n-grid-item>
              </n-grid>

            </template>
          </n-dynamic-input>
        </n-form-item-gi>

        <n-form-item-gi span=48 path="notes" label="Notes">
          <n-input type="textarea" v-model:value="compdoc.notes" @keydown.enter.prevent :readonly="popupMode == 'view'"
            :status="originalCompdoc.notes != compdoc.notes ? 'warning' : ''" />
        </n-form-item-gi>

        <n-form-item-gi span=48 path="path" label="Reference Path">
          <n-input v-model:value="compdoc.path" placeholder="Path" :readonly="popupMode == 'view'"
            @click="popupMode == 'view' ? copyToClipboard() : null" @keydown.enter.prevent />
        </n-form-item-gi>
      </n-grid>
      <n-collapse @item-header-click="handleItemHeaderClick">
        <n-collapse-item title="History" name="history">
          <n-scrollbar style="max-width: 60%">
            <n-timeline horizontal>
              <n-timeline-item
                :type="hobj.history_type == 'Created' ? 'success' : hobj.history_type == 'Changed' ? 'warning' : 'default'"
                :title="hobj.history_user" :time="hobj.history_date" v-for="(hobj, index) in compdoc.history"
                :key="index" />
              <n-text v-if="compdoc.history?.length == 0">
                No historical records.
              </n-text>
            </n-timeline>
          </n-scrollbar>
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
import { ICompDoc, IHistory } from '@/models/compdocs'
import { NModal, FormRules, FormInst } from 'naive-ui';
import { Edit24Regular } from '@vicons/fluent';
import { isoToTurkishDateTime, getTodayEUFormat } from '@/utils/time'
import { useOrgsStore } from '@/stores/api'
import { checkArrayEquals } from '@/utils/array'
import { statusOptions, statusColors, mocOptions, catOptions } from '@/stores/datatable'
import { validateForm } from '@/composables/forms';

const formRef = ref<FormInst | null>(null)

const rules = ref<FormRules>({
  name: [
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
  ],
  panel: [
    {
      required: true,
      trigger: "blur"
    }
  ],
})

const showModal = ref(false);
const compdoc = ref<ICompDoc>({} as ICompDoc)
const orgs = useOrgsStore()
let originalCompdoc: ICompDoc
const popupMode = ref<string | null>(null)
const hasExtraFields = ref(false)

function openModal(value: ICompDoc, mode: string) {
  popupMode.value = mode
  const dummy = JSON.parse(JSON.stringify(value))

  originalCompdoc = { ...dummy }
  compdoc.value = { ...dummy }
  hasExtraFields.value = window.$compdocStore.checkBonusFields()
  showModal.value = true;
}

function closeModal() {
  showModal.value = false;
}

async function addDatabase() {
  if (!await validateForm(formRef.value)) return
  await window.$compdocStore.createCompdoc(compdoc.value)
}

async function updateDatabase() {
  if (!await validateForm(formRef.value)) return
  await window.$compdocStore.updateCompdoc(compdoc.value.id, compdoc.value)
  closeModal()
}

function setPopupMode(mode: any) {
  popupMode.value = mode
}

function handleItemHeaderClick(value: any) {
  if (value.expanded && compdoc.value.history == null) {
    window.$compdocStore.fetchHistory(compdoc.value.id).then((res: IHistory[]) => {
      let history = res
      let newhistory = history.map((item: IHistory) => {
        return { ...item, history_date: isoToTurkishDateTime(item.history_date) }
      })
      compdoc.value.history = newhistory
    })
  }

}

async function copyToClipboard() {
  try {
    await navigator.clipboard.writeText(compdoc.value.path)
    window.$message.success("Path Copied")
  } catch (err) {
    console.error(err)
  }
}

defineExpose({ openModal })

onMounted(() => {

});
</script>
