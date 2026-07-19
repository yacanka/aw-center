<template>
  <n-button v-if="allowed" type="primary" @click="openModal">Create invitation link</n-button>
  <n-modal v-model:show="show" preset="dialog" title="Create user invitation" :style="modalStyle">
    <n-alert type="info" :bordered="false">
      The link is bound to one email, expires after 24 hours, and stops working after registration.
    </n-alert>
    <n-form ref="form" :model="model" :rules="rules" label-placement="top">
      <n-form-item label="Recipient email" path="email">
        <n-input v-model:value="model.email" :disabled="Boolean(result)" />
      </n-form-item>
      <n-form-item label="Initial groups">
        <n-select
          v-model:value="model.groupIds"
          multiple
          clearable
          :disabled="Boolean(result)"
          :options="groupOptions"
          placeholder="Optional groups"
        />
      </n-form-item>
    </n-form>
    <n-space v-if="result" vertical>
      <n-alert type="success">
        Link created for {{ result.email }}. It expires {{ formatDate(result.expires_at) }}.
      </n-alert>
      <n-input :value="result.invitation_link" type="textarea" readonly :autosize="linkSize" />
      <n-button type="primary" @click="copyLink">Copy link</n-button>
    </n-space>
    <template #action>
      <n-button v-if="!result" type="primary" :loading="creating" @click="createLink">
        Create link
      </n-button>
      <n-button v-else @click="closeModal">Done</n-button>
    </template>
  </n-modal>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import type { FormInst, FormRules } from 'naive-ui'
import type { IGroup } from '@/models/auth'
import { formatApiError } from '@/services/apiError'
import { createUserInvitation, type CreatedInvitation } from '@/services/userInvitations'
import { validateForm } from '@/composables/forms'

const props = defineProps<{ allowed: boolean; groups: IGroup[] }>()
const modalStyle = { width: 'min(680px, 90vw)' }
const linkSize = { minRows: 2, maxRows: 4 }
const rules: FormRules = {
  email: [
    { required: true, message: 'Recipient email is required.', trigger: ['blur', 'input'] },
    { type: 'email', message: 'Enter a valid email address.', trigger: ['blur', 'input'] }
  ]
}
const show = ref(false)
const creating = ref(false)
const form = ref<FormInst | null>(null)
const result = ref<CreatedInvitation | null>(null)
const model = ref({ email: '', groupIds: [] as number[] })
const groupOptions = computed(() =>
  props.groups.map((group) => ({ label: String(group.name), value: Number(group.id) }))
)

function openModal(): void {
  resetModel()
  show.value = true
}

function closeModal(): void {
  show.value = false
  resetModel()
}

function resetModel(): void {
  model.value = { email: '', groupIds: [] }
  result.value = null
}

async function createLink(): Promise<void> {
  if (!(await validateForm(form.value))) return
  creating.value = true
  try {
    result.value = await createUserInvitation(model.value.email, model.value.groupIds)
  } catch (error) {
    window.$message.error(formatApiError(error))
  } finally {
    creating.value = false
  }
}

async function copyLink(): Promise<void> {
  if (!result.value || !navigator.clipboard) {
    window.$message.warning('Copy the displayed link manually.')
    return
  }
  try {
    await navigator.clipboard.writeText(result.value.invitation_link)
    window.$message.success('Invitation link copied.')
  } catch {
    window.$message.warning('Copy the displayed link manually.')
  }
}

function formatDate(value: string): string {
  return new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(
    new Date(value)
  )
}
</script>
