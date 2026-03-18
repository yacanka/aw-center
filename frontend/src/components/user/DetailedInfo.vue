<template>
    <n-space vertical justify='space-around'>
        {{props.user?.id}} Still In Development
    </n-space>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { NSpace, NCard } from 'naive-ui';

const props = defineProps(['user'])

onMounted(() => {

});
</script>