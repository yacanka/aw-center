<template>
    <n-modal v-model:show="showModal" preset="dialog" title="DDF Summary" :on-after-leave="onAfterLeave"
        :style="{ width: '600px' }">
        <div style="height: 440px; display: flex; align-items: center;">
            <Pie :data="pieChartData" :options="pieChartOptions" :width="480" :height="360" />
        </div>

        <template #action>
            <n-button :onClick="closeModal"> OK </n-button>
        </template>
    </n-modal>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { Pie } from 'vue-chartjs'
import { IDdf } from '@/models/ddf'
import { pieChartOptions } from '@/stores/chartStore'

const showModal = ref(false)

const pieChartData = ref({
    labels: ['Teknik Görüş', 'Bilgi Görüşü', 'Editöryel Görüş', 'Panel Ekleme/Çıkarma'],
    datasets: [
        {
            data: [],
            radius: '90%',
            backgroundColor: ['#0ecfbf', '#c5252d', '#ffd966', '#1463bd'],
            hoverBorderWidth: 3,
            hoverBorderColor: '#aaaaaa',
        },
    ]
})

function openModal(ddfs: IDdf[]) {
    showModal.value = true
    calculatePieChart(ddfs)
}

function calculatePieChart(ddfs: IDdf[]) {
    const counter: Record<string, number> = {
        'Teknik Görüş': 0,
        'Bilgi Görüşü': 0,
        'Editöryel Görüş': 0,
        'Panel Ekleme/Çıkarma Görüşü': 0,
    }
    ddfs.forEach((ddf: IDdf) => {
        ddf.comment_types.forEach(type => {
            counter[type]++
        })
    })
    pieChartData.value.datasets[0].data = [counter['Teknik Görüş'], counter['Bilgi Görüşü'], counter['Editöryel Görüş'], counter['Panel Ekleme/Çıkarma Görüşü']]
}

function closeModal() {
    showModal.value = false
}

function onAfterLeave() {
}

defineExpose({
    openModal
})
</script>

<style>
.graph-item {
    display: none;
    transition: unset;
    height: 390px;
    width: 390px
}
</style>
