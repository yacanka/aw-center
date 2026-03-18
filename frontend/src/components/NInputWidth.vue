<template>
    <div class="auto-width-input">
        <n-input ref="inputRef" :value="value" :style="{ width: inputWidth + 'px' }" @input="updateValue" :placeholder="placeholder"
            :size="size" @blur="emit('blur')"/>
        <span ref="measureRef" class="measure-span" :style="{ fontSize: fontSize + 'px' }">{{ value || placeholder }}</span>
    </div>
</template>

<script setup>
import { ref, onMounted, nextTick } from 'vue'

const props = defineProps({
    value: {
        type: String,
        default: ''
    },
    size: {
        type: String,
        default: 'medium'
    },
    placeholder: {
        type: String,
        default: 'Input'
    }
})

const sizeValue = {
    tiny: {
        fontSize: 12,
        offsetWidth: 16
    },
    small: {
        fontSize: 14,
        offsetWidth: 22
    },
    medium: {
        fontSize: 14,
        offsetWidth: 28
    },
    large: {
        fontSize: 15,
        offsetWidth: 30
    },
}

const inputWidth = ref(30)
const inputRef = ref(null)
const measureRef = ref(null)

const offset = sizeValue[props.size].offsetWidth || sizeValue.medium.offsetWidth
const fontSize = sizeValue[props.size].fontSize || sizeValue.medium.fontSize

console.log(offset, fontSize)

const emit = defineEmits(['update:value', 'change', 'blur'])

function updateValue(value) {
    const span = measureRef.value
    if (!span) return
    emit('update:value', value)
    nextTick(() => {
        inputWidth.value = span.offsetWidth + offset
    })
}

onMounted(() => {
    updateValue(props.value)
    inputRef.value.focus()
})
</script>

<style scoped>
.auto-width-input {
    display: inline-block;
    position: relative;
}

.measure-span {
    visibility: hidden;
    white-space: pre;
    position: absolute;
    top: 0;
    left: 0;
    /*n-input fontuna eşit olmalı */
    padding: 0;
    margin: 0;
    font-family: inherit;
}
</style>