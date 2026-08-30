<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import Profil from '@/features/session/pages/Profile.vue'
import PasswordPopup from '@/features/session/components/settings/PasswordPopup.vue'
import { useSessionStore } from '@/features/session/stores/session'
import { applyPreferredTheme } from '@/app/services/theme'
import type { IPreferences } from '@/features/session/models/auth'

const router = useRouter()
const store = useSessionStore()

const LANGUAGES = [
  { label: 'English', value: 'en' },
  { label: 'Türkçe', value: 'tr', disabled: true }
]

const preferences = ref({
  theme: store.getPreferences.theme == 'dark' ? true : false,
  particle: store.getPreferences.has_particles,
  language: store.getPreferences.language
})

const passwordPopup = ref()

function handleThemeUpdate(value: boolean) {
  applyPreferredTheme({ theme: value ? 'dark' : 'light' })
  store.updatePreference({ theme: value ? 'dark' : 'light' })
}

function handlePrefUpdate(pref: IPreferences) {
  store.updatePreference(pref)
}

function openPasswordPopup() {
  passwordPopup.value.openModal()
}

async function logoutAction() {
  try {
    await store.logout()
    await router.push({ name: 'login' })
  } catch {
    // Do not present a failed server-side logout as a successful sign-out.
  }
}
</script>

<template>
  <n-flex justify="end">
    <Profil />
  </n-flex>
  <n-grid x-gap="18" y-gap="18" cols="1 640:2 1024:3" responsive="screen">
    <n-grid-item>
      <n-card title="Theme" size="small">
        <n-switch
          v-model:value="preferences.theme"
          @update:value="handleThemeUpdate"
          :style="{ width: '100%' }"
        >
          <template #checked> Dark </template>
          <template #unchecked> Light </template>
        </n-switch>
      </n-card>
    </n-grid-item>

    <n-grid-item>
      <n-card title="Particles" size="small">
        <n-switch
          v-model:value="preferences.particle"
          @update:value="(value: boolean) => handlePrefUpdate({ has_particles: value })"
          :style="{ width: '100%' }"
        >
          <template #checked> Enabled </template>
          <template #unchecked> Disabled </template>
        </n-switch>
      </n-card>
    </n-grid-item>

    <n-grid-item>
      <n-card title="Languages" size="small">
        <n-select
          v-model:value="preferences.language"
          size="small"
          :options="LANGUAGES"
          @update:value="(value: 'en' | 'tr') => handlePrefUpdate({ language: value })"
          :style="{ width: '100%' }"
        >
          <template #checked> Enabled </template>
          <template #unchecked> Disabled </template>
        </n-select>
      </n-card>
    </n-grid-item>

    <n-grid-item>
      <n-card size="small" @click="openPasswordPopup">
        <template #header>
          <div style="display: flex; justify-content: center">
            <n-button ghost :style="{ width: '100%' }"> Change Password </n-button>
          </div>
        </template>
      </n-card>
    </n-grid-item>

    <n-grid-item>
      <n-card size="small" @click="logoutAction">
        <template #header>
          <div style="display: flex; justify-content: center">
            <n-button type="error" ghost :style="{ width: '100%' }"> Logout </n-button>
          </div>
        </template>
      </n-card>
    </n-grid-item>
  </n-grid>
  <PasswordPopup ref="passwordPopup" />
</template>
