<template>
  <n-flex justify="center">
    <n-card title="Requirement PoC Linker" style="width: 80%">
      <n-p>
        Groups PoC requirements and automatically links them across modules.
      </n-p>
      <n-grid cols=12 x-gap=12 y-gap="18">
        <n-grid-item span=12>
          <n-input v-model:value="linker.ref_module_name" type="text" placeholder="Reference Module Name"
            @keydown.enter.prevent />
        </n-grid-item>
        <n-grid-item span=12>
          <n-input v-model:value="linker.target_module_name" type="text" placeholder="Target Module Name"
            @keydown.enter.prevent />
        </n-grid-item>
        <n-grid-item span=12>
          <n-input v-model:value="linker.link_module_name" type="text" placeholder="Link Module Name"
            @keydown.enter.prevent />
        </n-grid-item>
        <n-grid-item span=4>
          <n-input v-model:value="linker.ref_attr_poc" type="text" placeholder="Reference Module Attribute (PoC List)"
            @keydown.enter.prevent />
        </n-grid-item>
        <n-grid-item span=4>
          <n-input v-model:value="linker.ref_attr_req" type="text"
            placeholder="Reference Module Attribute (Requirement)" @keydown.enter.prevent />
        </n-grid-item>
        <n-grid-item span=4>
          <n-input v-model:value="linker.target_attr_poc" type="text" placeholder="Target Module Attribute (PoC Info)"
            @keydown.enter.prevent />
        </n-grid-item>
        <n-grid-item span=3>
          <n-input-number :value="parseInt(linker.start_index)" min="0" placeholder="Start Index"
            @update:value="handleStartIndexChange" />
        </n-grid-item>
        <n-grid-item span=3>
          <n-input-number :value="parseInt(linker.text_length)" min="-1" placeholder="Text Length"
            @update:value="handleTextLengthChange" />
        </n-grid-item>
        <n-grid-item span=3>
          <n-input v-model:value="testText" type="text" placeholder="Example Text" @keydown.enter.prevent />
        </n-grid-item>
        <n-grid-item span=3>
          <n-input :value="substr(testText)" type="text" placeholder="Text Result" readonly />
        </n-grid-item>

        <n-grid-item span=2 offset=0>
          <n-card size="small" title="Link Mode:">
            <template #header-extra>
              <n-switch size="small" v-model:value="linker.activeness" checked-value="true" unchecked-value="false">
                <template #checked>
                  Active
                </template>
                <template #unchecked>
                  Passive
                </template>
              </n-switch>
            </template>
          </n-card>
        </n-grid-item>

        <n-grid-item v-if="linker.activeness == 'true'" span=3>
          <n-card size="small" title="Link Direction:">
            <template #header-extra>
              <n-switch size="small" v-model:value="linker.direction" :theme-overrides="neutralSwitchTheme"
                checked-value="ref2tar" unchecked-value="tar2ref">
                <template #checked>
                  Reference → Target
                </template>
                <template #unchecked>
                  Target → Reference
                </template>
              </n-switch>
            </template>
          </n-card>
        </n-grid-item>

        <n-grid-item :span="linker.activeness == 'true' ? 7 : 10">
          <n-card size="small" style="height: 100%;">
            {{ linker.activeness == 'true' ?
              (modeDescriptions[0] + " Reference module will have " + (linker.direction == "tar2ref" ? '"In"'
                : '"Out"') + " type link.")
              :
              modeDescriptions[1] }}
          </n-card>
        </n-grid-item>
        <n-grid-item span=12 style="margin-top: -16px;">
          <n-flex justify="center" style="margin-top: 16px">
            <n-button @click="runDxl" :disabled="result.status == 'processing' ? true : false">
              {{ (linker.activeness == 'true' ? 'Link' : 'Show') }}
            </n-button>
          </n-flex>
        </n-grid-item>
        <n-grid-item span=12 v-if="result.content">
          <n-card title="Result" size="small">
            <n-text style="white-space: pre-wrap">
              {{ result.content }}
            </n-text>
          </n-card>
        </n-grid-item>
      </n-grid>
    </n-card>
  </n-flex>
</template>
<script setup>
import { ref, onMounted, computed } from 'vue';

import { setUser, getUser, isAuthenticated, logout, setProjectName } from "@/stores/user"
import { useDoorsStore } from '@/stores/api'
import { checkArrayEquals } from '@/utils/array'
import { NSwitch, useThemeVars } from 'naive-ui';

import { RouterLink, RouterView, useRouter } from 'vue-router'

const themeVars = useThemeVars()
const router = useRouter()
const store = useDoorsStore()

const modeDescriptions = [
  "It identifies potential links and creates them directly.",
  "It only identifies potential links but does not actually create them."
]
const directionDescriptions = [
  'Reference module will have "In" type link.',
  'Target module will have "Out" type link.',
]

const testText = ref("This is test text")

const neutralSwitchTheme = {
  railColor: themeVars.value.railColor,
  railColorActive: themeVars.value.railColor,
  buttonColor: themeVars.value.buttonColor
}

const linker = ref({
  mode: "req_poc_linker",
  ref_module_name: "",
  link_module_name: "",
  target_module_name: "",
  ref_attr_poc: "",
  ref_attr_req: "",
  target_attr_poc: "",
  start_index: "0",
  text_length: "-1",
  direction: "ref2tar",
  activeness: "false"
})

const result = ref({
  status: 'ok',
  content: '',
})

const createRailStyle = ({ focused, checked }) => {
  const style = {}
  if (checked) {
    style.background = "--n-rail-color"
    if (focused) {
      style.boxShadow = "0 0 0 2px #d0305040"
    }
  } else {
    style.background = "--n-rail-color"
    if (focused) {
      style.boxShadow = "0 0 0 2px #2080f040"
    }
  }
  return style
}

function substr(text) {
  if (linker.value.text_length == "-1") {
    return testText.value.substr(linker.value.start_index)
  }
  return testText.value.substr(linker.value.start_index, linker.value.text_length)
}

function handleStartIndexChange(value) {
  linker.value.start_index = value.toString()
}

function handleTextLengthChange(value) {
  linker.value.text_length = value.toString()
}

async function runDxl() {
  window.$loadingBar.start()
  result.value.status = 'processing'
  try {
    const res = await store.run_dxl(linker.value)
    result.value.content = res
    localStorage.setItem("poc_linker", JSON.stringify(linker.value))
    window.$loadingBar.finish()
  } catch (e) {
    window.$loadingBar.error()
  } finally {
    result.value.status = 'ok'
  }
}

onMounted(() => {
  const stored = localStorage.getItem("poc_linker")
  if (stored) {
    linker.value = JSON.parse(stored)
  }
})

</script>

<style scoped></style>
