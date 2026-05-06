<script setup lang="ts">
import { ref } from 'vue'
import { FormRules } from 'naive-ui'
import { useRouter, useRoute } from 'vue-router'
import { useAuthStore } from '@/stores/api'
import { validateForm } from '@/composables/forms'
import { useUserStore } from '@/stores/user'

const route = useRoute()
const router = useRouter()

type Status = "error" | "default" | "primary" | "info" | "success" | "warning"

interface Credentials {
  username: string,
  email: string,
  password: string,
  password2: string,
}

const signupCredentials = ref<Credentials>({} as Credentials)
const loginCredentials = ref<Credentials>({} as Credentials)

const userId = route.query.uid
const userToken = route.query.token
const newPasswordRequest = ref({
  uid: userId,
  token: userToken,
  password: "",
  passwordConfirm: ""
})

const loginForm = ref()
const signupForm = ref()
const resetPasswordForm = ref()

const userStore = useUserStore()

const forgotPasswordPopup = ref({
  visible: false,
  status: "default" as Status,
  footerText: "",
  email: ""
})

const rules: FormRules = {
  username: [
    { required: true, message: "Username required", trigger: "blur" },
    { min: 6, max: 6, message: "Need 6 character", trigger: "blur" }
  ],
  email: [
    { required: true, message: "Email required", trigger: "blur" },
    { type: "email", message: "Not available", trigger: "blur" }
  ],
  password: [
    { required: true, message: "Password required", trigger: "blur" }
  ],
  password2: [
    { required: true, message: "Password required", trigger: "blur" },
    {
      validator: (rule, value) => {
        if (value != signupCredentials.value.password) {
          return new Error("Passwords must match")
        }
        return true
      },
      trigger: ["blur"]
    }
  ]
}

const passwordConfirmRules: FormRules = {
  password: [
    { required: true, message: "Password required", trigger: "blur" }
  ],
  passwordConfirm: [
    { required: true, message: "Password required", trigger: "blur" },
    {
      validator: (rule, value) => {
        if (value != newPasswordRequest.value.password) {
          return new Error("Passwords must match")
        }
        return true
      },
      trigger: ["blur"]
    }
  ]
}

const authStore = useAuthStore()
async function handleLogin() {
  if (!await validateForm(loginForm.value)) return
  const isLoggedIn = await authStore.login(loginCredentials.value)
  if (!isLoggedIn) return

  await useUserStore().fetchCurrentUser()
  const systemTheme = window.matchMedia('(prefers-color-scheme: dark)').matches ? "dark" : "light"
  document.documentElement.setAttribute('data-theme', useUserStore().getPreferences.theme || systemTheme)
  router.push({ name: "home" })
}

async function handleSignup() {
  if (!await validateForm(signupForm.value)) return
  window.$authStore.signup(signupCredentials.value)
}

function onForgotPassword() {
  forgotPasswordPopup.value.visible = true
  forgotPasswordPopup.value.status = "default"
  forgotPasswordPopup.value.footerText = "A password reset link will be sent to your email."
}

async function sendPasswordResetRequest() {
  if (!await validateForm(resetPasswordForm.value)) return
  forgotPasswordPopup.value.status = "warning"
  forgotPasswordPopup.value.footerText = "Sending..."

  try {
    await userStore.resetPasswordRequest({ email: forgotPasswordPopup.value.email })
    forgotPasswordPopup.value.status = "success"
    window.$message.success("Check your inbox and follow the instructions to set a new password.", { duration: 5000 })
    forgotPasswordPopup.value.footerText = 'A password reset link has been sent to your email.'
  } catch (error) {
    forgotPasswordPopup.value.status = "error"
    forgotPasswordPopup.value.footerText = 'Something went wrong while sending reset link to your email.'
  }

}

async function handleUpdatePassword() {
  try {
    const res = await userStore.resetPasswordConfirm({
      uid: newPasswordRequest.value.uid,
      token: newPasswordRequest.value.token,
      new_password: newPasswordRequest.value.password
    })
    console.log(res)
    window.$message.success("Password updated successfully.", { duration: 5000 })
  } catch (error: any) {
    window.$message.error(error.detail, { duration: 5000 })
  }

}
</script>

<template>
  <n-space vertical justify="center" align="center" style="height: 60vh" item-style="width: 30vw; min-width: 400px">
    <div v-if="!userToken || !userId">
      <n-tabs placement="top">
        <n-tab-pane name="login" tab="Login">
          <n-card title="Login" size="large">
            <n-form ref="loginForm" :model="loginCredentials" size="large" :rules="rules" label-placement="top">
              <n-grid :x-gap="12" :cols="6">
                <n-form-item-gi span=6 label="Username" path="username">
                  <n-input v-model:value="loginCredentials.username" type="text"
                    placeholder="Enter your registration number" />
                </n-form-item-gi>
                <n-form-item-gi span=6 label="Password" path="password">
                  <n-input v-model:value="loginCredentials.password" type="password" placeholder="Enter your password"
                    show-password-on="mousedown" />
                </n-form-item-gi>
                <n-form-item-gi span=4>
                  <n-button type="primary" attr-type="submit" @click="handleLogin">Login</n-button>
                </n-form-item-gi>
                <n-form-item-gi span=2>
                  <n-tag checkable @click="onForgotPassword">
                    Forgot Password?
                  </n-tag>
                </n-form-item-gi>
              </n-grid>
            </n-form>
          </n-card>
        </n-tab-pane>
        <n-tab-pane name="signup" tab="Sign Up">
          <n-card title="Signup" size="large">
            <n-form ref="signupForm" :model="signupCredentials" size="large" :rules="rules" label-placement="top">
              <n-grid :x-gap="12" :cols="12">
                <n-form-item-gi span=6 label="Username" path="username">
                  <n-input v-model:value="signupCredentials.username" type="text"
                    placeholder="Enter your registration number" />
                </n-form-item-gi>
                <n-form-item-gi span=6 label="Email" path="email">
                  <n-input v-model:value="signupCredentials.email" type="email" placeholder="Enter your email" />
                </n-form-item-gi>
                <n-form-item-gi span=6 label="Password" path="password">
                  <n-input v-model:value="signupCredentials.password" type="password" placeholder="Enter your password"
                    show-password-on="mousedown" />
                </n-form-item-gi>
                <n-form-item-gi span=6 label="Password" path="password2">
                  <n-input v-model:value="signupCredentials.password2" type="password"
                    placeholder="Re-enter your password" show-password-on="mousedown" />
                </n-form-item-gi>
                <n-form-item-gi span=4>
                  <n-button type="primary" attr-type="submit" @click="handleSignup">Signup</n-button>
                </n-form-item-gi>
              </n-grid>
            </n-form>
          </n-card>
        </n-tab-pane>
      </n-tabs>
    </div>
    <div v-else>
      <n-card title="Set new password" size="large">
        <n-form ref="resetPasswordForm" :model="newPasswordRequest" size="large" :rules="passwordConfirmRules"
          label-placement="top">
          <n-grid :x-gap="12" :cols="6">
            <n-form-item-gi span=6 label="Password" path="password">
              <n-input v-model:value="newPasswordRequest.password" type="password" placeholder="Enter your new password"
                show-password-on="mousedown" />
            </n-form-item-gi>
            <n-form-item-gi span=6 label="Confirm Password" path="passwordConfirm">
              <n-input v-model:value="newPasswordRequest.passwordConfirm" type="password"
                placeholder="Enter your new password again" show-password-on="mousedown" />
            </n-form-item-gi>
            <n-form-item-gi span=6>
              <n-button type="primary" attr-type="submit" @click="handleUpdatePassword">Update</n-button>
            </n-form-item-gi>
          </n-grid>
        </n-form>
      </n-card>
    </div>
  </n-space>
  <n-modal v-model:show="forgotPasswordPopup.visible" preset="card" title="Reset Password" :style="{ width: '700px' }"
    :mask-closable="true" transform-origin="center">
    <n-form ref="resetPasswordForm" :model="forgotPasswordPopup" size="large" :rules="rules" label-placement="top">
      <n-grid :x-gap="12" :cols="12">
        <n-form-item-gi span=10 label="Email" path="email">
          <n-input v-model:value="forgotPasswordPopup.email" type="email" placeholder="Enter your email"
            :disabled="forgotPasswordPopup.status != 'default' && forgotPasswordPopup.status != 'error'" />
        </n-form-item-gi>
        <n-form-item-gi span=2>
          <n-button style="width: 100%" type="primary" attr-type="submit"
            :disabled="forgotPasswordPopup.status != 'default' && forgotPasswordPopup.status != 'error'"
            @click="sendPasswordResetRequest">Send</n-button>
        </n-form-item-gi>
      </n-grid>
      <n-tag style="width: 100%; justify-content: center;" :type="forgotPasswordPopup.status">
        {{ forgotPasswordPopup.footerText }}
      </n-tag>
    </n-form>
  </n-modal>
</template>
