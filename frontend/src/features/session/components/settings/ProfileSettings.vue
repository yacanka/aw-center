<script setup lang="ts">
import { computed, ref } from 'vue'
import type { FormInst, FormRules } from 'naive-ui'
import { useSessionStore } from '@/features/session/stores/session'
import { formatApiError } from '@/shared/api/apiError'

const store = useSessionStore()
const profile = ref({
  first_name: store.getUser.first_name || '',
  last_name: store.getUser.last_name || '',
  email: store.getUser.email || ''
})
const form = ref<FormInst>()
const saving = ref(false)
const error = ref('')
const changed = computed(() =>
  (Object.keys(profile.value) as (keyof typeof profile.value)[]).some(
    (field) => profile.value[field] !== (store.getUser[field] || '')
  )
)
const rules: FormRules = {
  first_name: { max: 150, message: 'Use at most 150 characters.', trigger: 'blur' },
  last_name: { max: 150, message: 'Use at most 150 characters.', trigger: 'blur' },
  email: [
    { required: true, message: 'Enter your email address.', trigger: 'blur' },
    { type: 'email', max: 254, message: 'Enter a valid email address.', trigger: 'blur' }
  ]
}

async function save() {
  if (saving.value || !changed.value) return
  try {
    await form.value?.validate()
  } catch {
    return
  }
  saving.value = true
  error.value = ''
  try {
    profile.value = await store.updateProfile({ ...profile.value })
  } catch (cause) {
    error.value = formatApiError(cause)
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <n-form ref="form" :model="profile" :rules="rules" :disabled="saving" @submit.prevent="save">
    <n-form-item label="First name" path="first_name" :label-props="{ for: 'profile-first-name' }">
      <n-input
        v-model:value="profile.first_name"
        :input-props="{ id: 'profile-first-name', autocomplete: 'given-name' }"
        :maxlength="150"
      />
    </n-form-item>
    <n-form-item label="Last name" path="last_name" :label-props="{ for: 'profile-last-name' }">
      <n-input
        v-model:value="profile.last_name"
        :input-props="{ id: 'profile-last-name', autocomplete: 'family-name' }"
        :maxlength="150"
      />
    </n-form-item>
    <n-form-item label="Email address" path="email" :label-props="{ for: 'profile-email' }">
      <n-input
        v-model:value="profile.email"
        :input-props="{ id: 'profile-email', autocomplete: 'email', inputmode: 'email' }"
        :maxlength="254"
      />
    </n-form-item>
    <p v-if="error" role="alert" class="profile-error">{{ error }}</p>
    <n-button attr-type="submit" type="primary" :loading="saving" :disabled="saving || !changed">
      Save profile
    </n-button>
  </n-form>
</template>

<style scoped>
.profile-error {
  margin: 0 0 16px;
  white-space: pre-line;
  overflow-wrap: anywhere;
}
</style>
