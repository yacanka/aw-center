<script setup lang="ts">
import { computed, ref } from 'vue'
import { FormRules } from 'naive-ui'
import { useRouter, useRoute } from 'vue-router'
import { useAuthStore } from '@/stores/api'
import { validateForm } from '@/composables/forms'
import { useUserStore } from '@/stores/user'
import { applyPreferredTheme } from '@/services/theme'
import PasswordRecovery from '@/components/user/PasswordRecovery.vue'
import { safePostLoginPath } from '@/services/accessPolicy'

const route = useRoute()
const router = useRouter()

interface Credentials {
  username: string
  password: string
}

const loginCredentials = ref<Credentials>({} as Credentials)

const userId = computed(() => queryString(route.query.uid))
const userToken = computed(() => queryString(route.query.token))
const loginForm = ref()
const passwordRecovery = ref<InstanceType<typeof PasswordRecovery> | null>(null)

const userStore = useUserStore()

const rules: FormRules = {
  username: [
    { required: true, message: 'Username required', trigger: 'blur' },
    { min: 3, max: 150, message: 'Username must be between 3 and 150 characters', trigger: 'blur' }
  ],
  password: [{ required: true, message: 'Password required', trigger: 'blur' }]
}

const authStore = useAuthStore()

async function handleLogin() {
  if (!(await validateForm(loginForm.value))) return
  const authenticatedUser = await authStore.login(loginCredentials.value)
  if (!authenticatedUser) return

  userStore.setUser(authenticatedUser)
  applyPreferredTheme(userStore.getPreferences)
  await router.replace(safePostLoginPath(route.query.redirect))
}

function openPasswordRecovery(): void {
  passwordRecovery.value?.openRequestModal()
}

function queryString(value: unknown): string {
  return typeof value === 'string' ? value : ''
}
</script>

<template>
  <n-space
    vertical
    justify="center"
    align="center"
    style="height: 60vh"
    item-style="width: 30vw; min-width: 400px"
  >
    <div v-if="!userToken || !userId">
      <n-tabs placement="top">
        <n-tab-pane name="login" tab="Login">
          <n-card title="Login" size="large">
            <n-form
              ref="loginForm"
              :model="loginCredentials"
              size="large"
              :rules="rules"
              label-placement="top"
            >
              <n-grid :x-gap="12" :cols="6">
                <n-form-item-gi span="6" label="Username" path="username">
                  <n-input
                    v-model:value="loginCredentials.username"
                    type="text"
                    placeholder="Enter your registration number"
                  />
                </n-form-item-gi>
                <n-form-item-gi span="6" label="Password" path="password">
                  <n-input
                    v-model:value="loginCredentials.password"
                    type="password"
                    placeholder="Enter your password"
                    show-password-on="mousedown"
                  />
                </n-form-item-gi>
                <n-form-item-gi span="4">
                  <n-button type="primary" attr-type="submit" @click="handleLogin">Login</n-button>
                </n-form-item-gi>
                <n-form-item-gi span="2">
                  <n-tag checkable @click="openPasswordRecovery"> Forgot Password? </n-tag>
                </n-form-item-gi>
              </n-grid>
            </n-form>
          </n-card>
        </n-tab-pane>
      </n-tabs>
    </div>
    <PasswordRecovery ref="passwordRecovery" :user-id="userId" :user-token="userToken" />
  </n-space>
</template>
