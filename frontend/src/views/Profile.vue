<script setup lang="ts">
import { h, ref, onMounted } from 'vue'
import { NButton, NDataTable, NSpace, NTag, NUpload } from 'naive-ui'
import {Settings16Regular, Door16Regular} from '@vicons/fluent';
import { useRouter } from 'vue-router'
import { logout, useUserStore} from "@/stores/user"

const router = useRouter()

const options = [
    {label: "Settings", key: "settings", icon: ()=> h(Settings16Regular, {style: "width: 28px"})},
    {label: "Logout", key: "logout", icon: ()=> h(Door16Regular, {style: "width: 28px"})},
]

const showNotification = ref(true)

function handleSelect(key: string | number){
    if(key == "settings"){
        router.push({name: "settings"})
    }else if(key == "logout"){
        logout()
        window.$authStore.logout().then(()=>{
            router.push({name: "login"})
        })
    }
}

const notificationValue = ref(1)

</script>

<template>
<n-dropdown trigger="hover" :options="options" @select="handleSelect">
  <n-badge processing :show=showNotification :value="notificationValue" :offset="[-4, 5]">
    <n-avatar round size="large"> {{ useUserStore().getUser.username }} </n-avatar>
  </n-badge>
</n-dropdown>
</template>