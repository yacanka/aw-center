<template>
    <n-space vertical justify='space-around'>
        <n-space justify='space-around'>
            <n-card v-if="props.compdoc.ubm_target_date">UBM Target Date: {{ props.compdoc.ubm_target_date }}</n-card>
            <n-card v-if="props.compdoc.ubm_delivery_date">UBM Delivery Date: {{ props.compdoc.ubm_delivery_date }}</n-card>
            <n-card v-if="props.compdoc.signature_panel">Signature Panel: {{ props.compdoc.signature_panel }}</n-card>
            <n-card v-if="props.compdoc.responsible">Responsbile: {{ props.compdoc.responsible }}</n-card>
            <n-card v-if="props.compdoc.moc">MoC: {{ props.compdoc.moc }}</n-card>
        </n-space>
        <n-space justify='space-around'>
        </n-space>
        <n-card v-if="props.compdoc.notes">Notes: {{ props.compdoc.notes }}</n-card>
    </n-space>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue';
import {NSpace, NCard} from 'naive-ui';

const props = defineProps(['compdoc'])

onMounted(() => {

});
</script>