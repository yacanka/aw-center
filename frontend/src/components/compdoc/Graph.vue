<template>
    <n-modal v-model:show="showModal" preset="dialog" title="Document Summary" :on-after-leave="onAfterLeave"
        :style="{ width: '600px' }">
        <div style="height: 440px; display: flex; align-items: center;">
            <n-tabs placement="top" v-model:value="activeTab" @update:value="handleTabChange">
                <n-tab-pane name="pie" tab="Pie Chart">
                    <Pie :data="pieChartData" :options="pieChartOptions" :width="480" :height="360" />
                </n-tab-pane>
                <n-tab-pane name="bar" tab="Bar Chart">
                    <Bar :data="barChartData" :options="barChartOptions" :width="480" :height="360" />
                </n-tab-pane>
                <n-tab-pane name="line" tab="Burndown Graph">
                    <Line :data="lineChartData" :options="getLineChartOptions(null, null)" :width="540" :height="360" />
                </n-tab-pane>
            </n-tabs>
        </div>

        <template #action>
            <n-button :onClick="closeModal"> OK </n-button>
        </template>
    </n-modal>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { Pie, Bar, Line } from 'vue-chartjs'
import { statusOptions, statusColors} from '@/stores/datatable'
import { calculateBarChart, calculatePieChart, calculateLineChart, pieChartOptions, barChartOptions, getLineChartOptions } from '@/stores/chartStore'
const SHOW_DELAYED_COMPDOCS = import.meta.env.SHOW_DELAYED_COMPDOCS
const showModal = ref(false);
const activeTab = ref(null)
const pieChartData = ref({
    labels: statusOptions.map(item => item.label),
    datasets: [
        {
            data: [],
            radius: '90%',
            backgroundColor: statusOptions.map(item => statusColors[item.value].color75),
            hoverBorderWidth: 3,
            hoverBorderColor: '#aaaaaa',
        },
    ]
})

const barChartData = ref({
    labels: ['Authority', 'UBM', 'AW'],
    datasets: [
        {
            data: [],
            radius: '90%',
            backgroundColor: ['#1463bd', '#cf750e', '#c5252d'],
            hoverBorderWidth: 3,
            hoverBorderColor: '#aaaaaa',
        },
    ]
})

const lineChartData = ref({
    datasets: [
        {
            label: "Now",
            data: [{ x: "2025-08-05", y: 30 }],
            borderColor: 'black',
            backgroundColor: 'red',
            pointBorderColor: 'black',
            pointBackgroundColor: 'red',
            pointRadius: 6,
            pointHoverRadius: 9,
        },
        {
            label: "Scheduled",
            data: [],
            backgroundColor: 'gray',
            borderColor: 'gray',
            borderDash: [5, 5],
            tension: 0.2
        },
        {
            label: "Actual",
            data: [40, 39, 10, 40, 80, 70],
            backgroundColor: 'orange',
            borderColor: 'orange',
            tension: 0.2
        },

    ]
})

function buildPieDataset(counter) {
    const dataset = [
        counter['to_be_issued'] + (SHOW_DELAYED_COMPDOCS ? 0 : counter['delayed']),
        counter['airworthiness_review'],
        counter['to_be_re-submitted'],
        counter['to_be_updated'],
        counter['authority_review'],
        counter['authority_approved'],
    ]

    if (SHOW_DELAYED_COMPDOCS) dataset.push(counter['delayed'])
    return dataset
}

function openModal(compdocs) {
    showModal.value = true

    const barCounter = calculateBarChart(compdocs)
    barChartData.value.datasets[0].data = [barCounter['authority'], barCounter['ubm'], barCounter['aw']]

    const pieCounter = calculatePieChart(compdocs)
    pieChartData.value.datasets[0].data = buildPieDataset(pieCounter)

    const lineCounter = calculateLineChart(compdocs)
    lineChartData.value.datasets[0].data = lineCounter['today']
    lineChartData.value.datasets[1].data = lineCounter['scheduled']
    lineChartData.value.datasets[2].data = lineCounter['actual']
}

onMounted(() => {
    const savedTab = localStorage.getItem("summaryActiveTab")
    activeTab.value = (savedTab ? savedTab : 'bar');
})

const handleTabChange = (tab) => {
    localStorage.setItem('summaryActiveTab', tab);
    activeTab.value = tab;
};

function closeModal() {
    showModal.value = false;
}

function onAfterLeave() {
    //activeTab.value = null
}

defineExpose({
    openModal
})
</script>

<style>

</style>