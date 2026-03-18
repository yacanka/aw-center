<template>
  <n-flex style="padding: 0px 300px">
    <n-tabs placement="top">
      <n-tab-pane name="ata_chapter" tab="Ata Chapter">
        <n-card title="Ata Chapter">
          <n-p>
            It verifies and reports on the presence of "ATA Chapter" depends on "Not Applicable".
          </n-p>
          <n-grid cols=12 x-gap=12 y-gap="18">
              <n-grid-item span=12>
                  <n-input v-model:value="agent1.module_path" type="text" placeholder="Module Path" @keydown.enter.prevent />
              </n-grid-item>
              <n-grid-item span=12 v-if="result">
                  <n-card title="Result" size="small">
                    {{ result }}
                  </n-card>
              </n-grid-item>
          </n-grid>
          <n-flex justify="center" style="margin-top: 16px">
            <n-button @click="checkDoors">
              Check
            </n-button>
          </n-flex>
        </n-card>
      </n-tab-pane>
    </n-tabs>

    </n-flex> 
</template>
<script setup>
import { ref, onMounted } from 'vue';

import { setUser, getUser, isAuthenticated, logout, setProjectName} from "@/stores/user"
import { useDoorsStore } from '@/stores/api'
import { checkArrayEquals } from '@/utils/array'

import { RouterLink, RouterView, useRouter } from 'vue-router'

const router = useRouter()
const store = useDoorsStore()

const agent1 = ref({
  module_path: "",
})

const agent2 = ref({
  module_path: "",
})

const result = ref(null)


function checkDoors(){
  store.checkAtaChapter(agent1.value).then((res)=>{
    result.value = res
  })
}

onMounted(()=>{

})

</script>

<style scoped>

</style>
