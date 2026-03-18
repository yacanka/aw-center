<template>
	<n-modal v-model:show="showModal" preset="dialog" title="Approve Information" centered
		:style="{ width: '60%', minWidth: '600px' }">
		<n-form ref="formRef" :rules="rules" :model="ecd">
			<n-grid cols=24 x-gap=12>
				<n-form-item-gi span=5 path="ecd_no" label="ECD No">
					<n-input v-model:value="ecd.ecd_no" placeholder="None" @keydown.enter.prevent />
				</n-form-item-gi>
				<n-form-item-gi span=3 path="project" label="Project">
					<n-input v-model:value="ecd.project" placeholder="None" @keydown.enter.prevent />
				</n-form-item-gi>
				<n-form-item-gi span=3 path="change_class" label="Class">
					<n-input v-model:value="ecd.change_class" placeholder="None" @keydown.enter.prevent />
				</n-form-item-gi>
				<n-form-item-gi span=5 path="cage_code" label="Cage Code">
					<n-input v-model:value="ecd.cage_code" placeholder="None" @keydown.enter.prevent />
				</n-form-item-gi>
				<n-form-item-gi span=4 path="change_type" label="Change Type">
					<n-input v-model:value="ecd.change_type" placeholder="None" @keydown.enter.prevent />
				</n-form-item-gi>
				<n-form-item-gi span=4 path="effectivity" label="Effectivity">
					<n-input v-model:value="ecd.effectivity" placeholder="None" @keydown.enter.prevent />
				</n-form-item-gi>

				<n-form-item-gi span=24 path="ecd_title" label="ECD Title">
					<n-input v-model:value="ecd.ecd_title" placeholder="None" @keydown.enter.prevent />
				</n-form-item-gi>

				<n-form-item-gi span=24 path="record_of_change" label="Record of Change">
					<n-input v-model:value="ecd.record_of_change" placeholder="None" @keydown.enter.prevent />
				</n-form-item-gi>

				<n-form-item-gi span=5 path="requestor" label="Requestor">
					<n-search v-model:value="ecd.requestor" placeholder="None" :list="orgstore.getPeople" />
				</n-form-item-gi>
				<n-form-item-gi span=3 path="ata" label="ATA / IDA">
					<n-input v-model:value="ecd.ata" placeholder="None" @keydown.enter.prevent />
				</n-form-item-gi>
				<n-form-item-gi span=3 path="subata" label="Sub-ATA">
					<n-input v-model:value="ecd.subata" placeholder="None" @keydown.enter.prevent />
				</n-form-item-gi>
				<n-form-item-gi span=5 path="ecd_initiator" label="ECD Initiator">
					<n-input v-model:value="ecd.ecd_initiator" placeholder="None" @keydown.enter.prevent />
				</n-form-item-gi>
				<n-form-item-gi span=3 path="status" label="Status">
					<n-input v-model:value="ecd.status" placeholder="None" @keydown.enter.prevent />
				</n-form-item-gi>

				<n-form-item-gi span=24 path="change_justification" label="Change Justification">
					<n-input v-model:value="ecd.change_justification" type="textarea" size="tiny" placeholder="None"
						@keydown.enter.prevent />
				</n-form-item-gi>
				<n-form-item-gi span=24 path="proposed_solution" label="Proposed Solution">
					<n-input v-model:value="ecd.proposed_solution" type="textarea" size="tiny" placeholder="None"
						@keydown.enter.prevent />
				</n-form-item-gi>
				<n-form-item-gi span=24 path="consequence" label="Consequence of non-implementation">
					<n-input v-model:value="ecd.consequence" type="textarea" size="tiny" placeholder="None"
						@keydown.enter.prevent />
				</n-form-item-gi>
				<n-form-item-gi span=24 path="impacted_groups" label="Impacted Groups">
					<n-input v-model:value="ecd.impacted_groups" type="textarea" size="tiny" placeholder="None"
						@keydown.enter.prevent />
				</n-form-item-gi>
			</n-grid>
		</n-form>
		<template #action>
			<n-button type="error" ghost @click="rejectInfo">Reject</n-button>
			<n-button type="success" ghost @click="approveInfo">Approve</n-button>
		</template>
	</n-modal>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { FormRules, NModal } from 'naive-ui';
import { IEcd } from '@/models/ecd';
import { validateForm } from '@/composables/forms';
import NSearch from '@/components/NSearch.vue';
import { useOrgsStore } from '@/stores/api';

const showModal = ref(false);
const ecd = ref<IEcd>({} as IEcd)
const formRef = ref()

const orgstore = useOrgsStore()
const rules: FormRules = {
	ecd_title: [
		{ required: true, trigger: "blur" },
	],
	ecd_no: [
		{ required: true, trigger: "blur" },
		{
			validator: (rule, value) => {
				if (!value.includes("/")) {
					return new Error("ECD number must include '/'")
				}
				return true
			},
			trigger: ["blur"]
		}
	],
	project: [
		{ required: true, trigger: "blur" },
	],
	requestor: [
		{ required: true, trigger: "blur" },
		{ min: 6, max: 6, message: "Need 6 character" }
	],
}

function openModal(value: IEcd) {
	ecd.value = value
	showModal.value = true;
}

function closeModal() {
	showModal.value = false;
}

async function approveInfo() {
	if (!await validateForm(formRef.value)) return
	props.onApprove?.(ecd.value)
	closeModal()
}

function rejectInfo() {
	props.onReject?.(ecd.value)
	closeModal()
}

const props = defineProps<{
	onApprove?: (data: IEcd) => void
	onReject?: (data: IEcd) => void
}>()

defineExpose({ openModal })

onMounted(() => {

});
</script>
