<script setup lang="ts">
import { h, ref, onMounted } from 'vue'
import { NButton, NDataTable, NIcon, NSpace, NTag, NUpload } from 'naive-ui'
import { useRouter } from 'vue-router'
import Profil from '@/views/Profile.vue'
import PasswordPopup from '@/components/settings/PasswordPopup.vue'
import { logout } from '@/stores/user';
import { IPreferences } from '@/models/auth';
import { useUserStore } from '@/stores/user';

const router = useRouter()
const store = useUserStore()

const LANGUAGES = [
    { label: "English", value: "en" },
    { label: "Türkçe", value: "tr", disabled: true },
]

const preferences = ref({
    theme: store.getPreferences.theme == 'dark' ? true : false,
    particle: store.getPreferences.has_particles,
    language: store.getPreferences.language
})

const passwordPopup = ref()

function handleThemeUpdate(value: boolean) {
    document.documentElement.setAttribute('data-theme', preferences.value.theme ? 'dark' : 'light')
    store.updatePreference({ theme: value ? 'dark' : 'light' })
}

function handlePrefUpdate(pref: object) {
    store.updatePreference(pref)
}


function openPasswordPopup() {
    passwordPopup.value.openModal()
}

function logoutAction() {
    logout()
    window.$authStore.logout().then(() => {
        router.push({ name: "login" })
    })
}

onMounted(() => {
    console.log(store.getPreferences.theme)
})
</script>

<template>
    <n-flex justify="end">
        <Profil />
    </n-flex>
    <n-grid x-gap="18" y-gap="18" cols=36>
        <n-grid-item span=3>
            <n-card title="Theme" size="small">
                <n-switch v-model:value="preferences.theme" @update:value="handleThemeUpdate"
                    :style="{ width: '100%' }">
                    <template #checked>
                        Dark
                    </template>
                    <template #unchecked>
                        Light
                    </template>
                </n-switch>
            </n-card>
        </n-grid-item>


        <n-grid-item span=5>
            <n-card title="Particles" size="small">
                <n-switch v-model:value="preferences.particle"
                    @update:value="(value: boolean) => handlePrefUpdate({ has_particles: value })"
                    :style="{ width: '100%' }">
                    <template #checked>
                        Enabled
                    </template>
                    <template #unchecked>
                        Disabled
                    </template>
                </n-switch>
            </n-card>
        </n-grid-item>

        <n-grid-item span=4>
            <n-card title="Languages" size="small">
                <n-select v-model:value="preferences.language" size="small" :options="LANGUAGES"
                    @update:value="(value: string) => handlePrefUpdate({ language: value })" :style="{ width: '100%' }">
                    <template #checked>
                        Enabled
                    </template>
                    <template #unchecked>
                        Disabled
                    </template>
                </n-select>
            </n-card>
        </n-grid-item>

        <n-grid-item span=24 />
        
        <n-grid-item span=5>
            <n-card size="small" @click="openPasswordPopup">
                <template #header>
                    <div style="display: flex; justify-content: center;">
                        <n-button ghost :style="{ width: '100%' }">
                            Change Password
                        </n-button>
                    </div>
                </template>
            </n-card>
        </n-grid-item>

        <n-grid-item span=5>
            <n-card size="small" @click="logoutAction">
                <template #header>
                    <div style="display: flex; justify-content: center;">
                        <n-button type="error" ghost :style="{ width: '100%' }">
                            Logout
                        </n-button>
                    </div>
                </template>
            </n-card>
        </n-grid-item>
    </n-grid>
    <PasswordPopup ref="passwordPopup" />
</template>