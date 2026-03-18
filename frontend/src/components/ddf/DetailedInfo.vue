<template>
    [ ID-{{ props.ddf?.id }} ] Still In Development
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue';

const props = defineProps(['ddf'])

onMounted(() => {

});
</script>